"""The compute-backend contract.

The HTTP API talks to the cube only through an :class:`Analyzer`. The reference
implementation is NumPy (:mod:`spektrify.compute.numpy_backend`); an accelerated one
(Rust via PyO3, CuPy, …) only has to provide the same methods and call
:func:`spektrify.compute.register_backend`. Array conventions: maps are ``(H, W)`` or
``(k, H, W)`` float32 with NaN for invalid pixels; spectra are ``(C,)``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from spektrify.model import Cube

F32 = NDArray[np.float32]


@runtime_checkable
class Analyzer(Protocol):
    cube: Cube

    # ---- statistics (cached by implementations)
    @property
    def finite_mask(self) -> NDArray[np.bool_]:
        """``(H, W)``: pixels whose whole spectrum is finite."""

    @property
    def band_stats(self) -> list[dict[str, float]]:
        """Per band: min max mean std p01 p99 … noise snr nan inf clip_hi clip_lo."""

    @property
    def global_range(self) -> dict[str, float]:
        """Cube-wide p005 p01 p99 p995 min max."""

    @property
    def mean_spectrum(self) -> NDArray[np.float64]: ...

    # ---- data quality
    @property
    def quality(self) -> dict[str, Any]:
        """Per-band metric lists, ``flags`` ([{band, reasons}]), ``issues`` (strings),
        ``bad_columns`` / ``bad_rows``."""

    @property
    def correlation(self) -> F32:
        """``(C, C)`` band-to-band correlation."""

    @property
    def stripe_profiles(self) -> dict[str, F32]:
        """``{"columns": (C, W), "rows": (C, H)}`` line-artifact scores in noise units."""

    # ---- products
    def pca(self, k: int = 10) -> dict[str, Any]:
        """``{"mean": (C,), "components": (k, C), "eigenvalues": (k,), "explained": [k]}``."""

    def project(self, k: int = 3, offset: int = 0) -> F32: ...
    def rx(self, k: int | None = None) -> F32: ...
    def pca_residual(self, k: int = 3) -> F32: ...
    def spectral_angle(self, reference: np.ndarray | None = None) -> F32: ...
    def spectral_gradient(self) -> F32: ...
    def summary_map(self, kind: str) -> F32: ...
    def band_math(self, expr: str) -> F32: ...

    # ---- sampling / geometry
    def region_stats(self, mask: NDArray[np.bool_]) -> dict[str, Any]: ...
    def line_profile(self, x0: float, y0: float, x1: float, y1: float) -> F32: ...
    def scatter_points(self, n: int = 40_000, k: int = 3) -> dict[str, Any]: ...
    def volume(
        self, max_xy: int = 192, max_c: int = 256
    ) -> tuple[NDArray[np.uint8], dict[str, Any]]: ...
    def thumbnails(self, max_side: int = 128) -> tuple[F32, dict[str, Any]]: ...
