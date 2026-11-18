"""MATLAB ``.mat`` reader (v5 via scipy, v7.3 via HDF5)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from spektrify.io._common import pick_cube_key, pick_wavelengths
from spektrify.io.base import RawArray, register_reader
from spektrify.io.hdf5_io import HDF5Reader


class MatReader:
    suffixes: tuple[str, ...] = (".mat",)

    def read(self, path: Path, *, dataset: str | None = None) -> RawArray:
        try:
            from scipy.io import loadmat
        except ImportError as e:  # pragma: no cover - optional dependency
            raise ImportError("Reading .mat files needs scipy: pip install scipy") from e
        try:
            raw = loadmat(path)
        except (NotImplementedError, ValueError):
            return HDF5Reader().read(path, dataset=dataset)  # v7.3 files are HDF5
        items = {k: np.asarray(v) for k, v in raw.items() if not k.startswith("__")}
        items = {k: v for k, v in items.items() if v.dtype.kind in "iufb"}
        key = pick_cube_key({k: v.shape for k, v in items.items()}, dataset)
        wl = pick_wavelengths({k: v for k, v in items.items() if k != key})
        return RawArray(items[key], wl, meta={"dataset": key})


register_reader(MatReader())
