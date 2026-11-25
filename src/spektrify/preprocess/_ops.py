"""Array kernels behind the preprocessing steps.

Plain functions on NumPy arrays, no Cube and no registry, so a faster implementation (Rust,
a GPU library) can replace any of them without touching the step classes. Cubes are
``(C, H, W)`` float32; NaN marks invalid pixels and is kept out of every estimate.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray

from spektrify._numeric import nanmean, nanmedian, robust_sigma

F32 = NDArray[np.float32]


# ------------------------------------------------------------------ bad pixels / lines


def local_median(img: F32, size: int) -> F32:
    """Median of the ``size × size`` neighbourhood of every pixel (NaN ignored)."""
    r = size // 2
    padded = np.pad(img, r, mode="reflect")
    windows = sliding_window_view(padded, (size, size)).reshape(*img.shape, size * size)
    fn = nanmedian if np.isnan(windows).any() else np.median
    return fn(windows, axis=-1).astype(np.float32)


def repair_lines(band: F32, axis: int, threshold: float, window: int = 5) -> F32:
    """Replace whole rows (``axis=0``) or columns (``axis=1``) that deviate from their
    neighbours by interpolating between the nearest good lines."""
    profile = nanmedian(band, axis=1 - axis)  # one value per line
    n = profile.size
    if n < window + 2:
        return band
    r = window // 2
    padded = np.pad(profile, r, mode="reflect")
    trend = nanmedian(sliding_window_view(padded, window), axis=-1)
    resid = profile - trend
    # Floor σ at 1 % of the profile's range: scenes with flat areas have MAD 0.
    spread = float(np.nanmax(profile) - np.nanmin(profile))
    sigma = max(robust_sigma(resid, empty=0.0), 0.01 * spread)
    if sigma <= 0:
        return band
    bad = np.abs(resid) > threshold * sigma
    if not bad.any() or bad.all():
        return band
    good = np.flatnonzero(~bad)
    out = band.copy()
    for i in np.flatnonzero(bad):
        lo = good[good < i]
        hi = good[good > i]
        if lo.size and hi.size:
            a, b = lo[-1], hi[0]
            w = (i - a) / (b - a)
            line = (1 - w) * _take(band, a, axis) + w * _take(band, b, axis)
        else:
            line = _take(band, lo[-1] if lo.size else hi[0], axis)
        if axis == 0:
            out[i, :] = line
        else:
            out[:, i] = line
    return out


def _take(band: F32, i: int, axis: int) -> F32:
    return band[i, :] if axis == 0 else band[:, i]


def repair_pixels(band: F32, size: int, threshold: float, fix_nonfinite: bool) -> F32:
    """Replace pixels that differ from their local median by more than ``threshold`` robust σ
    (and, optionally, NaN / Inf pixels) with that median."""
    work = band.copy()
    nonfinite = ~np.isfinite(work)
    work[nonfinite] = np.nan
    med = local_median(work, size)
    resid = work - med
    # A noise-free (piecewise constant) band has MAD 0, so floor σ at 1 % of the band's range.
    lo, hi = np.nanpercentile(work, (1, 99)) if np.isfinite(work).any() else (0.0, 0.0)
    sigma = max(robust_sigma(resid, empty=0.0), 0.01 * float(hi - lo))
    # A defect is isolated: beyond *all* its neighbours, not just the median. (This keeps
    # the corners of real objects, which differ from the median but match some neighbours.)
    r = size // 2
    windows = sliding_window_view(np.pad(work, r, mode="reflect"), (size, size))
    neigh = np.delete(windows.reshape(*work.shape, size * size), (size * size) // 2, axis=-1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        hi = np.nanmax(neigh, axis=-1)
        lo = np.nanmin(neigh, axis=-1)
    bad = np.zeros(work.shape, dtype=bool)
    if sigma > 0:
        with np.errstate(invalid="ignore"):
            bad = ((work - hi) > threshold * sigma) | ((lo - work) > threshold * sigma)
    if fix_nonfinite:
        bad |= nonfinite
    out = band.copy()
    out[bad] = med[bad]
    return out


# ------------------------------------------------------------------ flat field / balance


def poly_surface(img: F32, degree: int, step: int = 4) -> F32:
    """A smooth ``degree`` polynomial surface fitted to ``img`` (NaN ignored), evaluated at
    every pixel. Fitted on a subsampled grid, so cost is independent of the image size."""
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    y = (yy / max(h - 1, 1) * 2 - 1).astype(np.float64)
    x = (xx / max(w - 1, 1) * 2 - 1).astype(np.float64)
    terms = [(i, j) for i in range(degree + 1) for j in range(degree + 1 - i)]
    basis = np.stack([(x**i) * (y**j) for i, j in terms], axis=-1)
    sub = (slice(None, None, step), slice(None, None, step))
    z = img[sub].astype(np.float64)
    a = basis[sub].reshape(-1, len(terms))
    ok = np.isfinite(z.ravel())
    if ok.sum() < len(terms) * 4:
        raise ValueError("not enough valid pixels to fit an illumination surface")
    coef, *_ = np.linalg.lstsq(a[ok], z.ravel()[ok], rcond=None)
    return (basis @ coef).astype(np.float32)


def normalise_gain(gain: np.ndarray, min_gain: float) -> np.ndarray:
    """Scale a gain image(s) to unit median over the last two axes, floored at ``min_gain``."""
    med = nanmedian(gain, axis=(-2, -1))[..., None, None]
    med = np.where(np.isfinite(med) & (med != 0), med, 1.0)
    return np.maximum(gain / med, min_gain).astype(np.float32)


def band_gain_from_spectrum(ref: np.ndarray, target: float) -> F32:
    """Per-band multiplier mapping ``ref`` to ``target`` (bands with a zero / invalid
    reference are left unchanged)."""
    ref = np.asarray(ref, dtype=np.float64)
    ok = np.isfinite(ref) & (np.abs(ref) > 1e-12)
    gain = np.ones_like(ref)
    gain[ok] = target / ref[ok]
    return gain.astype(np.float32)


# ------------------------------------------------------------------ destriping


def destripe(data: F32, axis: int, window: int, mode: str) -> F32:
    """Remove per-column (``axis=1``) or per-row (``axis=0``) offsets / gains of every band.

    The stripe pattern is the difference between the line profile (median along the
    other axis) and its own running median, so structure wider than ``window`` pixels is kept.
    """
    c = data.shape[0]
    prof = nanmedian(data, axis=1 if axis == 1 else 2)  # (C, W) for columns / (C, H) for rows
    n = prof.shape[1]
    window = min(window | 1, (n // 2) * 2 - 1) if n > 2 else 1
    if window < 3:
        return data
    r = window // 2
    padded = np.pad(prof, ((0, 0), (r, r)), mode="reflect")
    trend = nanmedian(sliding_window_view(padded, window, axis=1), axis=-1)
    # The median of random stripes still wobbles a little; a running mean removes that.
    trend = np.nanmean(
        sliding_window_view(np.pad(trend, ((0, 0), (r, r)), mode="reflect"), window, axis=1),
        axis=-1,
    )
    prof = np.nan_to_num(prof)
    trend = np.nan_to_num(trend)
    shape = (c, 1, n) if axis == 1 else (c, n, 1)
    if mode == "gain":
        with np.errstate(divide="ignore", invalid="ignore"):
            g = np.where(np.abs(prof) > 1e-12, trend / prof, 1.0)
        return (data * g.reshape(shape)).astype(np.float32)
    return (data - (prof - trend).reshape(shape)).astype(np.float32)


# ------------------------------------------------------------------ spectral filters


def savgol_matrix(n: int, window: int, order: int, deriv: int, delta: float = 1.0) -> F32:
    """The ``(n, n)`` matrix applying a Savitzky-Golay filter along a length-``n`` axis.

    Interior rows use the classic centred coefficients; the first and last ``window // 2``
    rows evaluate the polynomial fitted to the first / last window, so no data is lost
    at the edges.
    """
    if window % 2 == 0 or window < 3:
        raise ValueError("window must be odd and ≥ 3")
    if order >= window:
        raise ValueError("order must be smaller than window")
    if not 0 <= deriv <= order:
        raise ValueError("deriv must be between 0 and order")
    if window > n:
        raise ValueError(f"window ({window}) is larger than the number of bands ({n})")
    half = window // 2
    x = np.arange(-half, half + 1, dtype=np.float64)
    fit = np.linalg.pinv(np.vander(x, order + 1, increasing=True))  # (order+1, window)

    def row(pos: float) -> np.ndarray:
        # derivative `deriv` of the fitted polynomial at `pos`, as weights on the window
        powers = np.zeros(order + 1)
        for k in range(deriv, order + 1):
            powers[k] = math.factorial(k) / math.factorial(k - deriv) * pos ** (k - deriv)
        return powers @ fit

    m = np.zeros((n, n))
    for i in range(n):
        start = min(max(i - half, 0), n - window)
        m[i, start : start + window] = row(i - start - half)
    return (m / delta**deriv).astype(np.float32)


def snv(data: F32) -> F32:
    """Standard normal variate: each pixel spectrum to zero mean, unit standard deviation."""
    mean = nanmean(data, axis=0)
    std = np.sqrt(nanmean((data - mean) ** 2, axis=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (data - mean) / std
    out[:, ~(std > 1e-12)] = np.nan
    return out.astype(np.float32)


def msc(data: F32, ref: np.ndarray) -> F32:
    """Multiplicative scatter correction: fit every pixel spectrum as ``a + b·ref`` and
    return ``(x − a) / b``."""
    ref = ref.astype(np.float64)
    r = ref - ref.mean()
    denom = float((r**2).sum())
    if denom <= 1e-24:
        raise ValueError("the reference spectrum is flat; MSC needs a spectrum with structure")
    x = data.astype(np.float64)
    xm = x.mean(axis=0)
    b = ((x - xm) * r[:, None, None]).sum(axis=0) / denom
    a = xm - b * ref.mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (x - a) / b
    out[:, ~(np.abs(b) > 1e-12)] = np.nan
    return out.astype(np.float32)


# ------------------------------------------------------------------ registration


def _prepare(band: F32) -> np.ndarray:
    """Gradient magnitude (brightness-invariant edges), windowed, for phase correlation."""
    img = np.nan_to_num(band, nan=float(nanmean(band)) if np.isfinite(band).any() else 0.0)
    gy, gx = np.gradient(img.astype(np.float64))
    g = np.hypot(gx, gy)
    g -= g.mean()
    win = np.outer(np.hanning(g.shape[0]), np.hanning(g.shape[1]))
    return g * win


def phase_correlate(ref_f: np.ndarray, band: F32, max_shift: float) -> tuple[float, float, float]:
    """Translation ``(dx, dy, confidence)`` such that ``band(y, x) ≈ ref(y − dy, x − dx)``.

    ``ref_f`` is ``rfft2(_prepare(ref))``. The peak is searched within ``max_shift`` pixels
    and refined to sub-pixel precision with a parabola. ``confidence`` is the height of the
    normalised correlation peak: about 0 for unrelated images, towards 1 for a clean match.
    """
    g = _prepare(band)
    if not np.any(g):
        return 0.0, 0.0, 0.0
    cross = np.fft.rfft2(g) * np.conj(ref_f)
    cross /= np.abs(cross) + 1e-9 * (np.abs(cross).mean() + 1e-30)
    corr = np.fft.irfft2(cross, s=g.shape)
    h, w = corr.shape
    m = math.ceil(max_shift)
    sub = np.full(corr.shape, -np.inf)
    ys = np.arange(-m, m + 1) % h
    xs = np.arange(-m, m + 1) % w
    sub[np.ix_(ys, xs)] = corr[np.ix_(ys, xs)]
    iy, ix = np.unravel_index(int(np.argmax(sub)), sub.shape)
    peak = float(corr[iy, ix])

    def refine(vm: float, v0: float, vp: float) -> float:
        d = vm - 2 * v0 + vp
        return 0.0 if abs(d) < 1e-12 else float(np.clip(0.5 * (vm - vp) / d, -0.5, 0.5))

    fy = refine(corr[(iy - 1) % h, ix], peak, corr[(iy + 1) % h, ix])
    fx = refine(corr[iy, (ix - 1) % w], peak, corr[iy, (ix + 1) % w])
    dy = (iy if iy <= h // 2 else iy - h) + fy
    dx = (ix if ix <= w // 2 else ix - w) + fx
    if math.hypot(dx, dy) > max_shift + 0.5:
        return 0.0, 0.0, 0.0
    return float(dx), float(dy), peak


def shift_image(img: F32, dx: float, dy: float) -> F32:
    """``out(y, x) = img(y − dy, x − dx)`` with bilinear interpolation; pixels that would
    come from outside the image become NaN."""
    out = img.astype(np.float32, copy=True)
    for axis, d in ((0, dy), (1, dx)):
        if d == 0:
            continue
        i = math.floor(d)
        f = d - i
        a = np.roll(out, i, axis=axis)
        out = a if f == 0 else (1 - f) * a + f * np.roll(out, i + 1, axis=axis)
        n = out.shape[axis]
        sl = [slice(None), slice(None)]
        if d > 0:
            sl[axis] = slice(0, min(math.ceil(d), n))
        else:
            sl[axis] = slice(max(n + i, 0), n)
        out[tuple(sl)] = np.nan
    return out.astype(np.float32)


def estimate_shifts(
    data: F32, reference: int, max_shift: float, min_confidence: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Per-band ``(dx, dy)`` against band ``reference`` and the confidence of each.

    Bands whose confidence is below ``min_confidence`` get a zero shift.
    """
    ref_f = np.fft.rfft2(_prepare(data[reference]))
    shifts = np.zeros((data.shape[0], 2))
    conf = np.zeros(data.shape[0])
    conf[reference] = 1.0
    for b in range(data.shape[0]):
        if b == reference:
            continue
        dx, dy, c = phase_correlate(ref_f, data[b], max_shift)
        conf[b] = c
        if c >= min_confidence:
            shifts[b] = (dx, dy)
    return shifts, conf
