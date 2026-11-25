"""Sensor and optics corrections: bad pixels, flat field, white balance, destriping, alignment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from spektrify._numeric import nanmean
from spektrify.model import Cube
from spektrify.preprocess import _ops as ops
from spektrify.preprocess import references as refs
from spektrify.preprocess.base import param, register_step


@register_step("badpixels", "Repair dead / hot pixels, dead rows and columns, and NaN pixels.")
@dataclass(frozen=True)
class BadPixels:
    threshold: float = param(6.0, "How many robust σ from the local median counts as defective.")
    size: int = param(3, "Neighbourhood for the median: 3 or 5 pixels.")
    lines: bool = param(True, "Also repair whole rows and columns that are off.")
    fix_nan: bool = param(True, "Replace NaN / Inf pixels by the local median.")

    def __call__(self, cube: Cube) -> Cube:
        if self.size not in (3, 5):
            raise ValueError("size must be 3 or 5")
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")
        data = cube.data.copy()
        for b in range(cube.n_bands):
            band = data[b]
            if self.lines:
                band = ops.repair_lines(band, 0, self.threshold)
                band = ops.repair_lines(band, 1, self.threshold)
            data[b] = ops.repair_pixels(band, self.size, self.threshold, self.fix_nan)
        return cube.with_data(data)


@register_step(
    "flatfield", "Divide out uneven illumination / vignetting (from a frame or estimated)."
)
@dataclass(frozen=True)
class FlatField:
    frame: str | np.ndarray = param(
        "",
        "Image of a uniform target: a 2-D file (all bands) or a cube of the same size. "
        "Empty = estimate a smooth surface from the data itself.",
        path=True,
    )
    dark: str | np.ndarray = param(
        "0", "Dark level subtracted from the frame (number, spectrum or cube file).", path=True
    )
    degree: int = param(2, "Polynomial degree of the estimated surface (no frame).")
    min_gain: float = param(0.05, "Never divide by less than this fraction of the mean level.")

    def __call__(self, cube: Cube) -> Cube:
        if refs.is_set(self.frame):
            frame = refs.image(self.frame, cube, what="flat-field frame")
            dark = refs.per_band(self.dark, cube, what="dark reference")
            frame = (
                np.broadcast_to(frame - dark, cube.data.shape)
                if frame.shape[0] == 1
                else (frame - dark)
            )
            gain = ops.normalise_gain(frame, self.min_gain)
        else:
            if self.degree < 0:
                raise ValueError("degree must be ≥ 0")
            mean_img = nanmean(cube.data, axis=0).astype(np.float32)
            gain = ops.normalise_gain(ops.poly_surface(mean_img, self.degree), self.min_gain)[None]
        return cube.with_data(cube.data / gain)


_BALANCE_METHODS = ("patch", "reference", "gray-world")


@register_step("whitebalance", "Equalise the bands using a gray patch, a spectrum or gray-world.")
@dataclass(frozen=True)
class WhiteBalance:
    method: str = param("patch", "patch (gray area), reference (spectrum file) or gray-world.")
    x0: int = param(0, "Patch: left column (inclusive).")
    y0: int = param(0, "Patch: top row (inclusive).")
    x1: int = param(0, "Patch: right column (exclusive; 0 = image edge).")
    y1: int = param(0, "Patch: bottom row (exclusive; 0 = image edge).")
    reference: str | np.ndarray = param(
        "", "Reference method: spectrum of a white / gray target.", path=True
    )
    target: float = param(1.0, "Level the reference becomes (1.0 = full reflectance).")

    def __call__(self, cube: Cube) -> Cube:
        if self.method not in _BALANCE_METHODS:
            raise ValueError(f"method must be one of {', '.join(_BALANCE_METHODS)}")
        if self.method == "patch":
            patch = cube.data[:, self.y0 : self.y1 or None, self.x0 : self.x1 or None]
            if patch.size == 0:
                raise ValueError("the patch is empty")
            ref = nanmean(patch.reshape(cube.n_bands, -1), axis=1)
        elif self.method == "reference":
            if not refs.is_set(self.reference):
                raise ValueError("method 'reference' needs a reference spectrum")
            ref = refs.spectrum(self.reference, cube, what="reference spectrum")
        else:  # gray-world: every band gets the same mean
            ref = nanmean(cube.data.reshape(cube.n_bands, -1), axis=1)
            target = float(np.nanmean(ref))
            gain = ops.band_gain_from_spectrum(ref, target)
            return cube.with_data(cube.data * gain[:, None, None])
        gain = ops.band_gain_from_spectrum(ref, self.target)
        return cube.with_data(cube.data * gain[:, None, None])


@register_step("destripe", "Remove column / row striping (typical of push-broom sensors).")
@dataclass(frozen=True)
class Destripe:
    axis: str = param("columns", "columns (vertical stripes) or rows (horizontal stripes).")
    mode: str = param("offset", "offset (additive) or gain (multiplicative) stripes.")
    window: int = param(31, "Structure wider than this many pixels is kept.")

    def __call__(self, cube: Cube) -> Cube:
        if self.axis not in ("columns", "rows"):
            raise ValueError("axis must be 'columns' or 'rows'")
        if self.mode not in ("offset", "gain"):
            raise ValueError("mode must be 'offset' or 'gain'")
        if self.window < 3:
            raise ValueError("window must be ≥ 3")
        data = ops.destripe(cube.data, 1 if self.axis == "columns" else 0, self.window, self.mode)
        return cube.with_data(data)


@register_step("align", "Register every band to a reference band (translation only).")
@dataclass(frozen=True)
class Align:
    reference: int = param(-1, "Band index to align to (−1 = the middle band).")
    max_shift: float = param(5.0, "Largest shift to look for, in pixels.")
    min_confidence: float = param(
        0.05, "Bands whose match is weaker than this are left where they are."
    )
    shifts: str | np.ndarray = param(
        "",
        "Skip estimation: a CSV with one 'dx,dy' row per band (as saved in meta align_shifts).",
        path=True,
    )

    def __call__(self, cube: Cube) -> Cube:
        ref = cube.n_bands // 2 if self.reference < 0 else self.reference
        if not 0 <= ref < cube.n_bands:
            raise ValueError(f"reference band {self.reference} is outside 0…{cube.n_bands - 1}")
        if self.max_shift <= 0:
            raise ValueError("max_shift must be positive")
        if refs.is_set(self.shifts):
            shifts = refs.load_shifts(self.shifts, cube.n_bands)
        else:
            if min(cube.height, cube.width) < 16:
                raise ValueError("image is too small to register")
            shifts, _ = ops.estimate_shifts(cube.data, ref, self.max_shift, self.min_confidence)
        data = cube.data.copy()
        for b in range(cube.n_bands):
            dx, dy = (float(v) for v in shifts[b])
            if dx or dy:
                data[b] = ops.shift_image(cube.data[b], -dx, -dy)
        out = cube.with_data(data)
        out.meta["align_shifts"] = [[round(float(dx), 3), round(float(dy), 3)] for dx, dy in shifts]
        return out
