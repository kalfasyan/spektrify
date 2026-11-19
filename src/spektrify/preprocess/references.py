"""Loading external calibration data (dark / white references, flat-field frames, spectra, shifts).

Every step that accepts a file goes through this module, so the accepted formats and the
error messages are the same everywhere. A *spec* is a number, a path string, or (in Python)
an array.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from spektrify.model import Cube

Spec = str | float | ArrayLike
Kind = Literal["spectrum", "image"]
_TEXT = (".txt", ".csv")


def is_set(spec: Spec | None) -> bool:
    """False for ``None`` and the empty string (an unset optional file parameter)."""
    return not (spec is None or (isinstance(spec, str) and not spec.strip()))


def load_array(spec: Spec) -> NDArray[np.float32]:
    """The raw content of a spec: an array of 0 (a number) to 3 dimensions.

    Text files (.txt, .csv) are read with ``numpy.loadtxt``, ``.npy`` with ``numpy.load``,
    and everything else with the cube readers (a 2-D TIFF comes back as one band).
    """
    if not isinstance(spec, str):
        return np.asarray(spec, dtype=np.float32)
    text = spec.strip()
    try:
        return np.asarray(float(text), dtype=np.float32)
    except ValueError:
        pass
    path = Path(text).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"reference file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in _TEXT:
        return np.atleast_1d(
            np.loadtxt(path, delimiter="," if suffix == ".csv" else None, dtype=np.float32)
        )
    if suffix == ".npy":
        return np.load(path).astype(np.float32, copy=False)
    from spektrify.io import load_cube

    return load_cube(path).data


def load_shifts(spec: Spec, n_bands: int) -> NDArray[np.float64]:
    """A ``(C, 2)`` table of per-band ``dx, dy`` shifts from a text, ``.csv`` or ``.npy`` file."""
    arr = np.asarray(load_array(spec), dtype=np.float64)
    if arr.ndim == 1 and arr.size % 2 == 0:
        arr = arr.reshape(-1, 2)  # a single "dx,dy" row
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"shifts must have two columns (dx, dy); got shape {arr.shape}")
    if arr.shape[0] != n_bands:
        raise ValueError(f"shifts has {arr.shape[0]} rows, cube has {n_bands} bands")
    return arr


def per_band(spec: Spec, cube: Cube, *, what: str = "reference") -> NDArray[np.float32]:
    """A reference that varies with wavelength, broadcastable against ``(C, H, W)``.

    Accepts a number, a spectrum of ``C`` values, or a cube of the same size (used per pixel).
    A cube of different spatial size is averaged to a spectrum.
    """
    ref = load_array(spec)
    if ref.ndim == 0:
        return ref
    if ref.ndim == 3:
        if ref.shape == cube.data.shape:
            return ref
        ref = np.nanmean(ref.reshape(ref.shape[0], -1), axis=1)
    if ref.ndim == 2 and 1 in ref.shape:
        ref = ref.ravel()
    if ref.ndim != 1 or ref.size != cube.n_bands:
        raise ValueError(
            f"{what} has {ref.size if ref.ndim == 1 else ref.shape} values, "
            f"cube has {cube.n_bands} bands"
        )
    return ref[:, None, None]


def spectrum(spec: Spec, cube: Cube, *, what: str = "reference") -> NDArray[np.float32]:
    """A reference spectrum ``(C,)``; a cube or image is averaged over its pixels."""
    ref = load_array(spec)
    if ref.ndim == 0:
        return np.full(cube.n_bands, ref, dtype=np.float32)
    if ref.ndim == 3:
        ref = np.nanmean(ref.reshape(ref.shape[0], -1), axis=1)
    ref = ref.ravel()
    if ref.size != cube.n_bands:
        raise ValueError(f"{what} has {ref.size} values, cube has {cube.n_bands} bands")
    return ref.astype(np.float32, copy=False)


def image(spec: Spec, cube: Cube, *, what: str = "frame") -> NDArray[np.float32]:
    """A reference image: ``(H, W)`` shared by all bands, or ``(C, H, W)`` per band.

    A cube with one band is treated as an image. Returns an array broadcastable to the cube.
    """
    ref = load_array(spec)
    if ref.ndim == 0:
        return ref
    if ref.ndim == 3 and ref.shape[0] == 1:
        ref = ref[0]
    if ref.ndim == 2:
        if ref.shape != (cube.height, cube.width):
            raise ValueError(
                f"{what} is {ref.shape[0]} × {ref.shape[1]}, cube is {cube.height} × {cube.width}"
            )
        return ref[None]
    if ref.ndim == 3 and ref.shape == cube.data.shape:
        return ref
    raise ValueError(
        f"{what} has shape {ref.shape}; expected {(cube.height, cube.width)} or {cube.data.shape}"
    )
