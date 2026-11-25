"""Spectral-axis preprocessing: smoothing / derivatives, SNV, MSC, absorbance."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from spektrify._numeric import nanmean
from spektrify.model import Cube
from spektrify.preprocess import _ops as ops
from spektrify.preprocess import references as refs
from spektrify.preprocess.base import param, register_step


@register_step("smooth", "Savitzky-Golay smoothing along the spectrum, optionally a derivative.")
@dataclass(frozen=True)
class Smooth:
    window: int = param(7, "Window length in bands (odd, ≥ 3).")
    order: int = param(2, "Polynomial order (smaller than the window).")
    deriv: int = param(0, "0 = smoothed spectrum, 1 or 2 = derivative (per wavelength unit).")

    def __call__(self, cube: Cube) -> Cube:
        delta = 1.0
        if cube.wavelengths is not None and cube.n_bands > 1:
            delta = float(np.mean(np.diff(cube.wavelengths)))
            delta = delta if delta else 1.0
        m = ops.savgol_matrix(cube.n_bands, self.window, self.order, self.deriv, delta)
        flat = cube.data.reshape(cube.n_bands, -1)
        return cube.with_data((m @ flat).reshape(cube.data.shape))


@register_step(
    "snv", "Standard normal variate: normalise each pixel spectrum (scatter, brightness)."
)
@dataclass(frozen=True)
class SNV:
    def __call__(self, cube: Cube) -> Cube:
        return cube.with_data(ops.snv(cube.data))


@register_step("msc", "Multiplicative scatter correction against a reference spectrum.")
@dataclass(frozen=True)
class MSC:
    reference: str | np.ndarray = param(
        "", "Reference spectrum file. Empty = the mean spectrum of the cube.", path=True
    )

    def __call__(self, cube: Cube) -> Cube:
        if refs.is_set(self.reference):
            ref = refs.spectrum(self.reference, cube, what="reference spectrum")
        else:
            ref = nanmean(cube.data.reshape(cube.n_bands, -1), axis=1)
        return cube.with_data(ops.msc(cube.data, np.nan_to_num(ref)))


@register_step("absorbance", "Convert reflectance to absorbance: −log10(R).")
@dataclass(frozen=True)
class Absorbance:
    floor: float = param(1e-4, "Reflectance below this is raised to it (avoids log of ≤ 0).")

    def __call__(self, cube: Cube) -> Cube:
        if self.floor <= 0:
            raise ValueError("floor must be positive")
        with np.errstate(invalid="ignore"):
            data = -np.log10(np.maximum(cube.data, self.floor))
        return cube.with_data(data)
