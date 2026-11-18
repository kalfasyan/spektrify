"""Built-in preprocessing steps. Each is a few lines of NumPy on the ``(C, H, W)`` cube."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from spektrify.model import Cube
from spektrify.preprocess.base import param, register_step


@register_step("clip", "Cap each band at a high percentile (suppresses specular highlights).")
@dataclass(frozen=True)
class Clip:
    percentile: float = param(99.98, "Per-band upper percentile, in (0, 100].")
    clip_negatives: bool = param(True, "Set values below zero (dark-level noise) to 0.")

    def __call__(self, cube: Cube) -> Cube:
        if not 0 < self.percentile <= 100:
            raise ValueError(f"percentile must be in (0, 100], got {self.percentile}")
        data = cube.data.copy()
        if self.clip_negatives:
            np.maximum(data, 0, out=data, where=np.isfinite(data))
        caps = np.nanpercentile(data.reshape(cube.n_bands, -1), self.percentile, axis=1)
        np.minimum(data, caps[:, None, None], out=data, where=np.isfinite(data))
        return cube.with_data(data)


@register_step(
    "calibrate", "Reflectance from dark and white references: (x − dark) / (white − dark)."
)
@dataclass(frozen=True)
class Calibrate:
    dark: str = param("0", "A number, or a file with a spectrum (C,) or a cube of the same size.")
    white: str = param("", "Same as dark. Empty = only subtract the dark level.")

    def __call__(self, cube: Cube) -> Cube:
        dark = _reference(self.dark, cube)
        data = cube.data - dark
        if self.white.strip():
            with np.errstate(divide="ignore", invalid="ignore"):
                data = data / (_reference(self.white, cube) - dark)
        return cube.with_data(data)


@register_step("crop", "Keep a rectangle of the image (0 for x1 / y1 means up to the edge).")
@dataclass(frozen=True)
class Crop:
    x0: int = param(0, "Left column (inclusive).")
    y0: int = param(0, "Top row (inclusive).")
    x1: int = param(0, "Right column (exclusive).")
    y1: int = param(0, "Bottom row (exclusive).")

    def __call__(self, cube: Cube) -> Cube:
        data = cube.data[:, self.y0 : self.y1 or None, self.x0 : self.x1 or None]
        if data.size == 0:
            raise ValueError("crop leaves an empty image")
        return cube.with_data(data)


@register_step("bands", "Keep a range of bands, e.g. to drop noisy ones at the edges.")
@dataclass(frozen=True)
class Bands:
    start: int = param(0, "First band to keep.")
    stop: int = param(0, "Band to stop before (0 = through the last band).")

    def __call__(self, cube: Cube) -> Cube:
        sel = slice(self.start, self.stop or None)
        if cube.data[sel].shape[0] == 0:
            raise ValueError("band range is empty")
        wl = None if cube.wavelengths is None else cube.wavelengths[sel]
        return cube.with_data(cube.data[sel], wavelengths=wl)


@register_step("bin", "Average f × f pixel blocks: less noise, smaller cube.")
@dataclass(frozen=True)
class Bin:
    factor: int = param(2, "Block size in pixels.")

    def __call__(self, cube: Cube) -> Cube:
        f = self.factor
        if f < 1:
            raise ValueError("bin factor must be ≥ 1")
        c, h, w = cube.data.shape
        hh, ww = h // f, w // f
        if not hh or not ww:
            raise ValueError("bin factor is larger than the image")
        blocks = cube.data[:, : hh * f, : ww * f].reshape(c, hh, f, ww, f)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN blocks stay NaN
            return cube.with_data(np.nanmean(blocks, axis=(2, 4)))


def _reference(spec: str, cube: Cube) -> np.ndarray | float:
    """A scalar, a per-band spectrum or a per-pixel cube, broadcastable to ``(C, H, W)``."""
    spec = spec.strip()
    try:
        return float(spec)
    except ValueError:
        pass
    from spektrify.io import load_cube

    path = Path(spec).expanduser()
    if path.suffix.lower() in (".txt", ".csv"):
        ref = np.loadtxt(path, delimiter="," if path.suffix.lower() == ".csv" else None)
    elif path.suffix.lower() == ".npy" and np.load(path, mmap_mode="r").ndim == 1:
        ref = np.load(path)
    else:
        ref_cube = load_cube(path)
        if ref_cube.data.shape == cube.data.shape:
            return ref_cube.data
        ref = np.nanmean(ref_cube.data.reshape(ref_cube.n_bands, -1), axis=1)
    ref = np.asarray(ref, dtype=np.float32).ravel()
    if ref.size != cube.n_bands:
        raise ValueError(
            f"{path.name}: reference has {ref.size} values, cube has {cube.n_bands} bands"
        )
    return ref[:, None, None]
