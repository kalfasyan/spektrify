"""Demosaicing of snapshot-mosaic (multispectral filter array) sensor images.

A ``t × t`` macropixel holds ``t²`` filters, so a raw ``(H, W)`` frame becomes a cube with
``t²`` channels, ordered by a row-major scan of the macropixel (the sensor layout). Methods
are registered by name so a better algorithm (or a sensor-specific one) can be added without
touching the loader.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

Demosaicer = Callable[[np.ndarray, int], np.ndarray]  # (H, W), tile -> (h, w, tile²)
_METHODS: dict[str, Demosaicer] = {}


def register_demosaicer(name: str, fn: Demosaicer) -> None:
    _METHODS[name] = fn


def demosaic_methods() -> list[str]:
    return sorted(_METHODS)


def demosaic(mosaic: np.ndarray, tile: int, method: str = "block") -> np.ndarray:
    """Unpack a 2-D mosaic into an ``(h, w, tile²)`` cube with the named method."""
    if tile < 2:
        raise ValueError("mosaic tile size must be at least 2")
    m = np.asarray(mosaic)
    if m.ndim != 2:
        raise ValueError(f"demosaicing needs a 2-D mosaic image, got shape {m.shape}")
    try:
        fn = _METHODS[method]
    except KeyError:
        raise ValueError(f"unknown demosaic method {method!r}; have {demosaic_methods()}") from None
    return fn(m, tile)


def _block(m: np.ndarray, t: int) -> np.ndarray:
    """One output pixel per macropixel (nearest neighbour). Fast, but channels are offset by
    up to ``t - 1`` sensor pixels from each other."""
    h, w = m.shape[0] // t, m.shape[1] // t
    return m[: h * t, : w * t].reshape(h, t, w, t).transpose(0, 2, 1, 3).reshape(h, w, t * t)


def _resample_axis(a: np.ndarray, offset: int, t: int, n_out: int, axis: int) -> np.ndarray:
    """Linearly interpolate samples taken at ``offset + t·i`` onto positions ``0..n_out-1``."""
    pos = (np.arange(n_out) - offset) / t
    i0 = np.clip(np.floor(pos).astype(int), 0, a.shape[axis] - 1)
    i1 = np.clip(i0 + 1, 0, a.shape[axis] - 1)
    f = np.clip(pos - i0, 0.0, 1.0).astype(np.float32)
    shape = [1] * a.ndim
    shape[axis] = n_out
    f = f.reshape(shape)
    return np.take(a, i0, axis=axis) * (1 - f) + np.take(a, i1, axis=axis) * f


def _bilinear(m: np.ndarray, t: int) -> np.ndarray:
    """Full sensor resolution: each channel is bilinearly interpolated from its own sample
    grid, which also removes the sub-macropixel misregistration between channels."""
    h, w = (m.shape[0] // t) * t, (m.shape[1] // t) * t
    m = m[:h, :w].astype(np.float32)
    out = np.empty((h, w, t * t), np.float32)
    for dy in range(t):
        rows = _resample_axis(m[dy::t], dy, t, h, axis=0)
        for dx in range(t):
            out[..., dy * t + dx] = _resample_axis(rows[:, dx::t], dx, t, w, axis=1)
    return out


register_demosaicer("block", _block)
register_demosaicer("bilinear", _bilinear)
