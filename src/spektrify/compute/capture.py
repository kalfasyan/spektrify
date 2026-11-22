"""Simulations of how a camera captures an image: the sensor, the lens, colour filter
arrays and line scanning.

They exist to *teach*: each takes ideal images (as band math produces them) and returns what a
simple, explicitly stated camera would record, so a lesson can show an effect before naming
it. Plain NumPy, ``(H, W)`` float32 out, NaN-aware like :mod:`spektrify.compute.imageops`,
deterministic (fixed random seeds), and exposed to band math by name
(:data:`BANDMATH_FUNCTIONS`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from spektrify.compute.imageops import F32, _clamp, _out, _prep
from spektrify.io.demosaic import demosaic as _demosaic_frame

# --------------------------------------------------------------------------- the sensor

PHOTONS_PER_UNIT = 1000.0
"""Electrons collected by a pixel whose input value is 1 at exposure ``t = 1`` (the light that
reaches the pixel × its quantum efficiency × the exposure time, folded into one number)."""
FULL_WELL = 10_000.0
"""Electrons a pixel can hold before it saturates."""
READ_NOISE = 5.0
"""Standard deviation, in electrons, of the noise the readout electronics add."""


def expose(img: Any, t: float = 1.0, bits: float = 12) -> F32:
    """What a simple sensor records, in digital counts (DN), when ``img`` is the light
    reaching each pixel (1 = a white surface) and ``t`` the exposure.

    The chain: mean electrons = ``PHOTONS_PER_UNIT · t · img``; the actual number is drawn
    from a Poisson distribution (shot noise); the readout adds Gaussian noise of
    ``READ_NOISE`` electrons; the pixel clips at ``FULL_WELL``; the ADC maps 0..FULL_WELL to
    0..2^bits − 1 and rounds.
    """
    a, bad = _prep(img)
    rng = np.random.default_rng(0)
    mean_e = np.clip(a, 0, None) * PHOTONS_PER_UNIT * _clamp(t, 0, 1000)
    electrons = rng.poisson(np.minimum(mean_e, 1e9)).astype(np.float64)
    electrons += rng.normal(0.0, READ_NOISE, a.shape)
    electrons = np.clip(electrons, 0, FULL_WELL)
    top = 2.0 ** int(_clamp(bits, 1, 16)) - 1
    return _out(np.round(electrons / FULL_WELL * top), bad)


# --------------------------------------------------------------------------- the lens


def defocus(img: Any, r: float = 3) -> F32:
    """Out-of-focus blur: the average over a disc of radius ``r`` pixels. A defocused point
    spreads into a uniform disc (the shape of the aperture), not into a Gaussian."""
    a, bad = _prep(img)
    rr = _clamp(r, 0, 12)
    n = int(np.ceil(rr))
    if n == 0:
        return _out(a, bad)
    yy, xx = np.mgrid[-n : n + 1, -n : n + 1]
    disc = (np.hypot(xx, yy) <= rr + 0.5).astype(np.float32)
    disc /= disc.sum()
    win = sliding_window_view(np.pad(a, n, mode="reflect"), disc.shape)
    return _out(np.einsum("ijkl,kl->ij", win, disc), bad)


# --------------------------------------------------------------------------- colour filter arrays


def _bayer_masks(shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Where an RGGB Bayer sensor has its red, green and blue filters."""
    yy, xx = np.indices(shape)
    red = (yy % 2 == 0) & (xx % 2 == 0)
    blue = (yy % 2 == 1) & (xx % 2 == 1)
    return red, ~(red | blue), blue


def bayer(r: Any, g: Any = None, b: Any = None) -> F32:
    """The raw frame of an RGGB Bayer sensor: each pixel keeps only the one colour its filter
    passes (red at even rows and columns, blue at odd ones, green in between). With one
    image, the scene is grey: all three colours equal it."""
    g, b = (r if g is None else g), (r if b is None else b)
    (ra, bad), (ga, _), (ba, _) = _prep(r), _prep(g), _prep(b)
    if not ra.shape == ga.shape == ba.shape:
        raise ValueError("bayer() needs three images of the same size")
    red, _green, blue = _bayer_masks(ra.shape)
    return _out(np.where(red, ra, np.where(blue, ba, ga)), bad)


_KERNEL_RB = np.array([[0.25, 0.5, 0.25], [0.5, 1, 0.5], [0.25, 0.5, 0.25]], np.float32)
_KERNEL_G = np.array([[0, 0.25, 0], [0.25, 1, 0.25], [0, 0.25, 0]], np.float32)


def debayer(raw: Any, c: float = 1) -> F32:
    """Bilinear demosaicing of an RGGB raw frame: channel ``c`` (0 red, 1 green, 2 blue) at
    every pixel, the measured value where the filter matches and the average of the nearest
    measured neighbours elsewhere (the textbook baseline)."""
    a, bad = _prep(raw)
    ch = int(_clamp(c, 0, 2))
    mask = _bayer_masks(a.shape)[ch]
    k = _KERNEL_G if ch == 1 else _KERNEL_RB
    win = sliding_window_view(np.pad(np.where(mask, a, 0), 1, mode="reflect"), (3, 3))
    wts = sliding_window_view(np.pad(mask.astype(np.float32), 1, mode="reflect"), (3, 3))
    num = np.einsum("ijkl,kl->ij", win, k)
    den = np.einsum("ijkl,kl->ij", wts, k)
    return _out(num / np.maximum(den, 1e-6), bad)


def demosaic(raw: Any, t: float = 4, i: float = 0) -> F32:
    """Band ``i`` of a ``t × t`` snapshot-mosaic frame (see ``mosaic(t)``), bilinearly
    interpolated from the pixels that carry that filter."""
    a, bad = _prep(raw)
    tile = int(_clamp(t, 2, 8))
    h, w = (a.shape[0] // tile) * tile, (a.shape[1] // tile) * tile
    if h == 0 or w == 0:
        raise ValueError("the image is smaller than one mosaic tile")
    band = _demosaic_frame(a, tile, "bilinear")[..., int(_clamp(i, 0, tile * tile - 1))]
    out = np.pad(band, ((0, a.shape[0] - h), (0, a.shape[1] - w)), mode="edge")
    return _out(out, bad)


def mosaic_frame(cube_chw: np.ndarray, t: float = 4) -> F32:
    """The raw frame of a ``t × t`` snapshot-mosaic sensor looking at the cube ``(C, H, W)``:
    ``t²`` evenly spaced bands, and pixel ``(y, x)`` sees band number ``(y % t)·t + x % t``
    of them. Same size as the cube; band math calls it as ``mosaic(t)``."""
    tile = int(_clamp(t, 2, 8))
    c, h, w = cube_chw.shape
    picks = np.round(np.linspace(0, c - 1, tile * tile)).astype(int)
    yy, xx = np.indices((h, w))
    which = picks[(yy % tile) * tile + xx % tile]
    return np.asarray(cube_chw[which, yy, xx], dtype=np.float32)


# --------------------------------------------------------------------------- line scanning


def scan(img: Any, speed: float = 1, wobble: float = 0) -> F32:
    """What a push-broom (line-scan) camera records when the object moves ``speed`` image
    rows per captured line (1 = matched to the line rate) and each line is shifted sideways
    by a smooth random amount with a spread of ``wobble`` pixels (vibration). Rows past the
    end of the object are NaN."""
    a, bad = _prep(img)
    h, w = a.shape
    v = _clamp(speed, 0.1, 10)
    pos = np.arange(h) * v
    rng = np.random.default_rng(0)
    side = np.convolve(rng.normal(0, 1, h + 8), np.ones(9) / 3, mode="valid")[:h]
    side *= _clamp(wobble, 0, 20)
    y0 = np.clip(np.floor(pos).astype(int), 0, h - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    fy = (pos - np.floor(pos))[:, None]
    rows = a[y0] * (1 - fy) + a[y1] * fy
    xs = np.arange(w)[None, :] - side[:, None]
    out = np.stack([np.interp(xs[i], np.arange(w), rows[i]) for i in range(h)])
    out[pos > h - 1] = np.nan
    lost = bad[y0] | bad[y1]
    return _out(out, lost)


BANDMATH_FUNCTIONS: dict[str, Callable[..., Any]] = {
    f.__name__: f for f in (expose, defocus, bayer, debayer, demosaic, scan)
}
"""Capture simulations band math can call by name; ``mosaic(t)`` is added by the backend
because it needs the whole cube."""
