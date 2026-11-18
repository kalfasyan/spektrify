"""The viewer's data model: an in-memory spectral cube.

Cubes are stored band-major as ``float32`` with shape ``(C, H, W)``: fetching a band (the
hot path while scrubbing) is a contiguous slice and a pixel spectrum is a cheap strided read.
This module has no I/O and no analysis code, so every other layer can depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass
class Cube:
    """A spectral cube held band-major: ``data`` has shape ``(C, H, W)``."""

    data: NDArray[np.float32]
    wavelengths: NDArray[np.float64] | None = None
    name: str = "cube"
    source: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.data.ndim != 3:
            raise ValueError(f"Cube data must be (C, H, W); got shape {self.data.shape}")
        self.data = np.ascontiguousarray(self.data, dtype=np.float32)
        if self.wavelengths is not None:
            wl = np.asarray(self.wavelengths, dtype=np.float64).ravel()
            if wl.size != self.n_bands:
                wl = None
            self.wavelengths = wl

    @property
    def n_bands(self) -> int:
        return int(self.data.shape[0])

    @property
    def height(self) -> int:
        return int(self.data.shape[1])

    @property
    def width(self) -> int:
        return int(self.data.shape[2])

    @property
    def axis(self) -> NDArray[np.float64]:
        """Spectral axis values: wavelengths when known, else band indices."""
        if self.wavelengths is not None:
            return self.wavelengths
        return np.arange(self.n_bands, dtype=np.float64)

    @property
    def axis_unit(self) -> str:
        return str(self.meta.get("wavelength_units", "nm")) if self.wavelengths is not None else ""

    def json_meta(self) -> dict[str, Any]:
        """The JSON-serialisable subset of ``meta``."""
        out = {}
        for k, v in self.meta.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[k] = v
            elif isinstance(v, (list, tuple)) and all(isinstance(x, (str, int, float)) for x in v):
                out[k] = list(v)
        return out

    @classmethod
    def from_array(
        cls,
        array: ArrayLike,
        wavelengths: ArrayLike | None = None,
        *,
        layout: str = "auto",
        name: str = "array",
        source: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Cube:
        """Build a cube from any 2-D or 3-D array.

        ``layout`` names the axis order of ``array``: ``"hwc"`` (channels last, the numpy /
        OpenCV convention), ``"chw"`` (channels first, the PyTorch convention), or
        ``"auto"`` to guess from the shape (the smallest of the first and last axes is the
        spectral one).
        """
        arr = _to_numpy(array)
        arr = np.squeeze(arr) if arr.ndim > 3 else arr
        if arr.ndim == 2:
            arr = arr[None, :, :]
            layout = "chw"
        if arr.ndim != 3:
            raise ValueError(f"Expected a 2-D or 3-D array, got shape {arr.shape}")
        layout = resolve_layout(arr.shape, layout, n_wavelengths=_len_or_none(wavelengths))
        chw = np.moveaxis(arr, -1, 0) if layout == "hwc" else arr
        meta = dict(meta or {})
        meta.setdefault("source_dtype", str(arr.dtype))
        meta.setdefault("source_layout", layout)
        if np.issubdtype(arr.dtype, np.integer):
            meta.setdefault("dtype_max", float(np.iinfo(arr.dtype).max))
        return cls(
            data=np.ascontiguousarray(chw, dtype=np.float32),
            wavelengths=None if wavelengths is None else np.asarray(wavelengths, dtype=float),
            name=name,
            source=source,
            meta=meta,
        )


def _len_or_none(x: ArrayLike | None) -> int | None:
    if x is None:
        return None
    return int(np.asarray(x).size)


def _to_numpy(array: ArrayLike) -> np.ndarray:
    # Accept torch tensors / xarray / dask without importing them.
    for attr in ("detach",):
        if hasattr(array, attr):
            array = array.detach().cpu().numpy()  # type: ignore[union-attr]
    if hasattr(array, "values") and not isinstance(array, np.ndarray):
        array = array.values  # xarray
    return np.asarray(array)


def resolve_layout(shape: tuple[int, ...], layout: str, n_wavelengths: int | None = None) -> str:
    """Return ``"hwc"`` or ``"chw"`` for a 3-D ``shape``."""
    layout = layout.lower()
    if layout in ("hwc", "chw"):
        return layout
    if layout != "auto":
        raise ValueError(f"layout must be 'auto', 'hwc' or 'chw', got {layout!r}")
    first, last = shape[0], shape[-1]
    if n_wavelengths is not None:
        if last == n_wavelengths and first != n_wavelengths:
            return "hwc"
        if first == n_wavelengths and last != n_wavelengths:
            return "chw"
    return "chw" if first < last else "hwc"
