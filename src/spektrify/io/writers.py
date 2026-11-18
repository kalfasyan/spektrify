"""Saving cubes and raw mosaics. Files are written as ``(H, W, C)`` plus wavelengths, the
layout the readers in this package (and most other tools) pick up without options."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from spektrify.model import Cube

CUBE_SUFFIXES = (".npz", ".h5", ".hdf5")


def save_cube(cube: Cube, path: str | Path) -> Path:
    """Write ``cube`` to ``.npz`` or ``.h5`` (datasets ``cube`` and ``wavelengths``)."""
    path = Path(path)
    hwc = cube.data.transpose(1, 2, 0)
    arrays = (
        {"cube": hwc}
        if cube.wavelengths is None
        else {"cube": hwc, "wavelengths": cube.wavelengths}
    )
    suffix = path.suffix.lower()
    if suffix == ".npz":
        np.savez_compressed(path, **arrays)  # ty: ignore[invalid-argument-type]
    elif suffix in (".h5", ".hdf5"):
        import h5py

        with h5py.File(path, "w") as f:
            for name, arr in arrays.items():
                f.create_dataset(name, data=arr, compression="gzip", compression_opts=4)
            f["cube"].attrs["layout"] = "hwc"
    else:
        raise ValueError(f"can't write {suffix!r}; use one of {CUBE_SUFFIXES}")
    return path


def save_raw_mosaic(mosaic: np.ndarray, wavelengths: np.ndarray, path: str | Path) -> Path:
    """Write a 2-D sensor frame in spektro's raw HDF5 layout (``mosaic_image`` +
    ``central_wavelengths``), which :func:`spektrify.io.load_cube` demosaics on open."""
    import h5py

    path = Path(path)
    with h5py.File(path, "w") as f:
        f.create_dataset("mosaic_image", data=mosaic, compression="gzip", compression_opts=4)
        f["central_wavelengths"] = np.asarray(wavelengths, dtype=np.float64)
    return path
