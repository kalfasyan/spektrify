"""Classic image operations on one band: point operations, filters, edges, the Fourier
domain, morphology, connected regions, corners and k-means.

Plain NumPy functions: 2-D arrays in, ``(H, W)`` float32 out (``otsu`` returns a number).
Non-finite pixels are filled with the image median before filtering and are NaN again in the
result. Band math exposes them by name (:data:`BANDMATH_FUNCTIONS`), which is how the Learn
lessons and the viewer's band-math box use them; a faster backend can replace this module
function by function. Parameters are clamped to sensible ranges so a typo in the UI can't
start a huge computation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray

F32 = NDArray[np.float32]


# --------------------------------------------------------------------------- helpers


def _prep(img: Any) -> tuple[F32, NDArray[np.bool_]]:
    """``img`` as float32 with non-finite pixels filled, plus the mask of those pixels."""
    a = np.asarray(img, dtype=np.float32)
    if a.ndim != 2:
        raise ValueError("this function takes one image, e.g. nm(670) or b[10]")
    bad = ~np.isfinite(a)
    if bad.any():
        a = a.copy()
        a[bad] = float(np.median(a[~bad])) if (~bad).any() else 0.0
    return a, bad


def _out(a: Any, bad: NDArray[np.bool_]) -> F32:
    out = np.asarray(a, dtype=np.float32).copy()
    out[bad] = np.nan
    return out


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(min(max(float(v), lo), hi))


def _windows(a: F32, size: int, axis: int, mode: str) -> NDArray[np.float32]:
    """Sliding windows of ``size`` along ``axis`` (last dimension), padded to keep the shape."""
    r = size // 2
    pad = ((r, r), (0, 0)) if axis == 0 else ((0, 0), (r, r))
    padded = np.pad(a, pad, mode=mode)  # ty: ignore[no-matching-overload]
    return sliding_window_view(padded, size, axis=axis)


def _separable(a: F32, kernel: NDArray[np.float32]) -> F32:
    """Convolve rows, then columns, with the same symmetric 1-D ``kernel``."""
    mode = "reflect" if len(kernel) // 2 < min(a.shape) else "edge"
    a = _windows(a, len(kernel), 1, mode) @ kernel
    return _windows(a, len(kernel), 0, mode) @ kernel


def _rank(a: F32, r: int, fn: Callable[..., Any]) -> F32:
    """Separable square min / max filter of side ``2r + 1``."""
    a = fn(_windows(a, 2 * r + 1, 1, "edge"), axis=-1)
    return fn(_windows(a, 2 * r + 1, 0, "edge"), axis=-1)


def _range01(a: F32) -> tuple[float, float]:
    lo, hi = float(np.min(a)), float(np.max(a))
    return lo, (hi if hi > lo else lo + 1.0)


# --------------------------------------------------------------------------- point operations


def stretch(img: Any, lo: float = 2, hi: float = 98) -> F32:
    """Linear contrast stretch: the ``lo``-th percentile maps to 0, the ``hi``-th to 1."""
    a, bad = _prep(img)
    p_lo, p_hi = np.percentile(a[~bad] if (~bad).any() else a, [lo, hi])
    return _out(np.clip((a - p_lo) / max(float(p_hi - p_lo), 1e-12), 0, 1), bad)


def quantize(img: Any, levels: float = 8) -> F32:
    """Keep only ``levels`` evenly spaced grey levels between the image's min and max."""
    a, bad = _prep(img)
    n = int(_clamp(levels, 2, 65536))
    lo, hi = _range01(a)
    return _out(np.round((a - lo) / (hi - lo) * (n - 1)) / (n - 1), bad)


def equalize(img: Any, bins: float = 256) -> F32:
    """Histogram equalisation: map each value to the fraction of pixels below it (0..1)."""
    a, bad = _prep(img)
    vals = a[~bad] if (~bad).any() else a.ravel()
    hist, edges = np.histogram(vals, bins=int(_clamp(bins, 2, 4096)))
    cdf = np.cumsum(hist) / max(int(hist.sum()), 1)
    return _out(np.interp(a, (edges[:-1] + edges[1:]) / 2, cdf), bad)


def otsu(img: Any) -> float:
    """Otsu's threshold: the value that best splits the histogram into two classes (it
    maximises the variance between the classes)."""
    a, bad = _prep(img)
    vals = a[~bad] if (~bad).any() else a.ravel()
    hist, edges = np.histogram(vals, bins=256)
    p = hist / max(int(hist.sum()), 1)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(p)
    m0 = np.cumsum(p * centers)
    with np.errstate(all="ignore"):
        between = (m0[-1] * w0 - m0) ** 2 / (w0 * (1 - w0))
    between[~np.isfinite(between)] = -1
    return float(edges[int(np.argmax(between)) + 1])


def subsample(img: Any, f: float = 4) -> F32:
    """Keep every ``f``-th pixel in each direction and blow it back up (no smoothing), to
    show what sampling does."""
    a, bad = _prep(img)
    k = int(_clamp(f, 1, 64))
    small = a[::k, ::k]
    big = np.repeat(np.repeat(small, k, axis=0), k, axis=1)[: a.shape[0], : a.shape[1]]
    return _out(big, bad)


# --------------------------------------------------------------------------- linear filters


def box(img: Any, r: float = 1) -> F32:
    """Mean of the ``(2r + 1)²`` square around each pixel."""
    a, bad = _prep(img)
    n = 2 * int(_clamp(r, 0, 25)) + 1
    return _out(_separable(a, np.full(n, 1 / n, np.float32)), bad)


def gauss(img: Any, sigma: float = 1) -> F32:
    """Gaussian blur with standard deviation ``sigma`` pixels."""
    a, bad = _prep(img)
    s = _clamp(sigma, 0.3, 20)
    x = np.arange(-int(np.ceil(3 * s)), int(np.ceil(3 * s)) + 1, dtype=np.float32)
    k = np.exp(-(x**2) / (2 * s * s))
    return _out(_separable(a, (k / k.sum()).astype(np.float32)), bad)


def _sobel(a: F32, axis: int) -> F32:
    """Sobel derivative along ``axis`` (1 = x, left to right; 0 = y, top to bottom)."""
    smooth = np.array([0.25, 0.5, 0.25], np.float32)
    diff = np.array([-0.5, 0, 0.5], np.float32)  # window @ diff = (right - left) / 2
    d = _windows(a, 3, axis, "reflect") @ diff
    return _windows(d, 3, 1 - axis, "reflect") @ smooth


def dx(img: Any) -> F32:
    """Horizontal derivative (Sobel): positive where the image gets brighter to the right."""
    a, bad = _prep(img)
    return _out(_sobel(a, 1), bad)


def dy(img: Any) -> F32:
    """Vertical derivative (Sobel): positive where the image gets brighter downwards."""
    a, bad = _prep(img)
    return _out(_sobel(a, 0), bad)


def grad(img: Any) -> F32:
    """Gradient magnitude ``sqrt(dx² + dy²)``: how fast the image changes, in any direction."""
    a, bad = _prep(img)
    return _out(np.hypot(_sobel(a, 1), _sobel(a, 0)), bad)


def laplace(img: Any) -> F32:
    """Laplacian (sum of the four neighbours minus four times the centre): the second
    derivative, zero on flat areas and ramps, large at fine detail and noise."""
    a, bad = _prep(img)
    p = np.pad(a, 1, mode="reflect")
    lap = p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * a
    return _out(lap, bad)


def median(img: Any, r: float = 1) -> F32:
    """Median of the ``(2r + 1)²`` square around each pixel (``r`` up to 3)."""
    a, bad = _prep(img)
    n = 2 * int(_clamp(r, 1, 3)) + 1
    win = sliding_window_view(np.pad(a, n // 2, mode="edge"), (n, n))
    return _out(np.median(win, axis=(-2, -1)), bad)


# --------------------------------------------------------------------------- frequency domain


def fft(img: Any) -> F32:
    """Log magnitude of the 2-D Fourier transform, zero frequency in the centre. The image
    is tapered to zero at its borders first (a Hann window), so the jump between opposite
    edges doesn't draw a bright cross through the centre."""
    a, _ = _prep(img)
    window = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1])).astype(np.float32)
    spec = np.fft.fftshift(np.fft.fft2((a - a.mean()) * window))
    return np.log1p(np.abs(spec)).astype(np.float32)


def _gauss_transfer(shape: tuple[int, ...], cutoff: float) -> NDArray[np.float64]:
    fy = np.fft.fftfreq(shape[0])[:, None]
    fx = np.fft.fftfreq(shape[1])[None, :]
    f = np.hypot(fx, fy) / 0.5  # 1 = the Nyquist frequency
    return np.exp(-0.5 * (f / _clamp(cutoff, 0.005, 2)) ** 2)


def lowpass(img: Any, cutoff: float = 0.1) -> F32:
    """Keep frequencies below ``cutoff`` (a fraction of the highest one, 0..1), smoothly."""
    a, bad = _prep(img)
    out = np.fft.ifft2(np.fft.fft2(a) * _gauss_transfer(a.shape, cutoff)).real
    return _out(out, bad)


def highpass(img: Any, cutoff: float = 0.1) -> F32:
    """What :func:`lowpass` removes: the image minus its low frequencies."""
    a, bad = _prep(img)
    out = np.fft.ifft2(np.fft.fft2(a) * (1 - _gauss_transfer(a.shape, cutoff))).real
    return _out(out, bad)


# --------------------------------------------------------------------------- morphology


def erode(img: Any, r: float = 1) -> F32:
    """Minimum over a ``(2r + 1)²`` square: shrinks bright shapes, removes small ones."""
    a, bad = _prep(img)
    return _out(_rank(a, int(_clamp(r, 1, 25)), np.min), bad)


def dilate(img: Any, r: float = 1) -> F32:
    """Maximum over a ``(2r + 1)²`` square: grows bright shapes, fills small gaps."""
    a, bad = _prep(img)
    return _out(_rank(a, int(_clamp(r, 1, 25)), np.max), bad)


def opening(img: Any, r: float = 1) -> F32:
    """Erode, then dilate: removes bright specks smaller than the square, keeps the rest."""
    return dilate(erode(img, r), r)


def closing(img: Any, r: float = 1) -> F32:
    """Dilate, then erode: fills dark holes and gaps smaller than the square."""
    return erode(dilate(img, r), r)


# --------------------------------------------------------------------------- regions


def _label(img: Any) -> NDArray[np.intp]:
    """8-connected components of ``img > 0.5``, numbered 1, 2, … from the largest; 0 is
    the background. Labels spread by repeated 3 × 3 maxima until nothing changes."""
    a = np.nan_to_num(np.asarray(img, dtype=np.float32), nan=0.0)
    if a.ndim != 2:
        raise ValueError("this function takes one mask, e.g. nm(800) > 0.4")
    mask = a > 0.5
    lab = np.where(mask, np.arange(1, mask.size + 1, dtype=np.float32).reshape(mask.shape), 0)
    for _ in range(mask.size):
        nxt = np.where(mask, _rank(lab, 1, np.max), 0)
        if np.array_equal(nxt, lab):
            break
        lab = nxt
    ids, inverse, counts = np.unique(lab, return_inverse=True, return_counts=True)
    fg = ids > 0
    rank = np.zeros(ids.size, np.intp)
    order = np.argsort(-counts[fg], kind="stable")
    rank[np.flatnonzero(fg)[order]] = np.arange(1, int(fg.sum()) + 1)
    return rank[inverse.reshape(mask.shape)]


def components(img: Any) -> F32:
    """Number each connected region of a mask: 1 is the largest, 0 the background."""
    return _label(img).astype(np.float32)


def area(img: Any) -> F32:
    """The size, in pixels, of the connected region each pixel belongs to (0 outside)."""
    lab = _label(img)
    counts = np.bincount(lab.ravel())
    counts[0] = 0
    return counts[lab].astype(np.float32)


# --------------------------------------------------------------------------- features


def harris(img: Any, sigma: float = 1.5, k: float = 0.05) -> F32:
    """Harris corner response, scaled so the strongest corner is 1. Positive at corners
    (the image changes in every direction), negative along edges, about 0 on flat areas."""
    a, bad = _prep(img)
    ix, iy = _sobel(a, 1), _sobel(a, 0)
    sxx, syy, sxy = (gauss(v, sigma) for v in (ix * ix, iy * iy, ix * iy))
    resp = sxx * syy - sxy * sxy - k * (sxx + syy) ** 2
    peak = float(np.max(np.abs(resp)))
    return _out(resp / peak if peak > 0 else resp, bad)


# --------------------------------------------------------------------------- clustering


def kmeans(x: NDArray[np.floating[Any]], k: int, iters: int = 30, seed: int = 0) -> F32:
    """Lloyd's k-means on the rows of ``x`` (``(N, D)``) with k-means++ seeding. Returns
    ``(k, D)`` centres, sorted by their mean value so the numbering is stable."""
    x = np.asarray(x, dtype=np.float64)
    k = int(min(max(k, 1), len(x)))
    rng = np.random.default_rng(seed)
    centres = x[[int(rng.integers(len(x)))]]
    for _ in range(1, k):
        d2 = np.min(_sq_dist(x, centres), axis=1)
        total = float(d2.sum())
        pick = int(rng.choice(len(x), p=d2 / total)) if total > 0 else int(rng.integers(len(x)))
        centres = np.vstack([centres, x[pick]])
    for _ in range(iters):
        assign = np.argmin(_sq_dist(x, centres), axis=1)
        new = np.array(
            [x[assign == j].mean(axis=0) if np.any(assign == j) else centres[j] for j in range(k)]
        )
        if np.allclose(new, centres):
            break
        centres = new
    return centres[np.argsort(centres.mean(axis=1))].astype(np.float32)


def nearest(x: NDArray[np.floating[Any]], centres: NDArray[np.floating[Any]]) -> NDArray[np.intp]:
    """Index of the nearest centre (Euclidean) for each row of ``x``."""
    return np.argmin(_sq_dist(np.asarray(x, np.float64), np.asarray(centres, np.float64)), axis=1)


def _sq_dist(x: NDArray[np.float64], c: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.maximum((x * x).sum(1)[:, None] - 2 * x @ c.T + (c * c).sum(1)[None, :], 0)


BANDMATH_FUNCTIONS: dict[str, Callable[..., Any]] = {
    f.__name__: f
    for f in (
        stretch,
        quantize,
        equalize,
        otsu,
        subsample,
        box,
        gauss,
        median,
        dx,
        dy,
        grad,
        laplace,
        fft,
        lowpass,
        highpass,
        erode,
        dilate,
        opening,
        closing,
        components,
        area,
        harris,
    )
}
"""Image functions band math can call by name (all take one image first)."""
