"""HDF5 reader (also MATLAB v7.3 files). Recognises spektro's raw-mosaic format."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from spektrify.io._common import WAVELENGTH_KEYS, pick_cube_key, pick_wavelengths
from spektrify.io.base import RawArray, register_reader


class HDF5Reader:
    suffixes = (".h5", ".hdf5", ".he5")

    def read(self, path: Path, *, dataset: str | None = None) -> RawArray:
        import h5py

        with h5py.File(path, "r") as f:
            shapes: dict[str, tuple[int, ...]] = {}
            small: dict[str, np.ndarray] = {}

            def visit(name: str, obj: Any) -> None:
                if isinstance(obj, h5py.Dataset) and obj.dtype.kind in "iufb":
                    shapes[name] = tuple(obj.shape)
                    if obj.ndim <= 2 and obj.size <= 4096:
                        small[name] = obj[()]

            f.visititems(visit)
            tile = None
            if dataset is None and len(shapes.get("mosaic_image", ())) == 2:
                # spektro's own format: a raw 4×4 snapshot mosaic.
                key, tile = "mosaic_image", 4
            else:
                key = pick_cube_key(shapes, dataset)
            ds = f[key]
            arr = ds[()]
            wl = pick_wavelengths({k: v for k, v in small.items() if k != key})
            if wl is None:
                for attr in WAVELENGTH_KEYS:
                    if attr in ds.attrs:
                        wl = np.asarray(ds.attrs[attr], dtype=float).ravel()
                        break
        return RawArray(arr, wl, meta={"dataset": key}, mosaic_tile=tile)


register_reader(HDF5Reader())
