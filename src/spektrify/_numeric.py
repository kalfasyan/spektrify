"""Small NaN-aware NumPy helpers shared by every layer (compute, preprocessing, the API).

Kept free of any spektrify import so that any module can depend on it.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np

MAD_TO_SIGMA = 1.4826
"""Scale from the median absolute deviation to the standard deviation of a Gaussian."""


def finite_list(a: Any) -> list[float | None]:
    """Flatten to a JSON-safe list: non-finite values become ``None``."""
    arr = np.asarray(a, dtype=np.float64).ravel()
    return [float(v) if np.isfinite(v) else None for v in arr]


def nanmean(a: np.ndarray, axis: int | tuple[int, ...] | None = None) -> np.ndarray:
    """``np.nanmean`` without the warning for all-NaN slices (they give NaN)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a, axis=axis)


def nanmedian(a: np.ndarray, axis: int | tuple[int, ...] | None = None) -> np.ndarray:
    """``np.nanmedian`` without the warning for all-NaN slices (they give NaN)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(a, axis=axis)


def robust_sigma(x: np.ndarray, *, empty: float = float("nan")) -> float:
    """Noise level of ``x`` from its median absolute deviation (ignores outliers and
    non-finite values); ``empty`` when nothing is finite."""
    x = x[np.isfinite(x)]
    if x.size == 0:
        return empty
    return float(MAD_TO_SIGMA * np.median(np.abs(x - np.median(x))))
