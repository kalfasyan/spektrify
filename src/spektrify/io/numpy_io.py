"""NumPy ``.npy`` / ``.npz`` readers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from spektrify.io._common import pick_cube_key, pick_wavelengths, sidecar_wavelengths
from spektrify.io.base import RawArray, register_reader


class NpyReader:
    suffixes = (".npy",)

    def read(self, path: Path, *, dataset: str | None = None) -> RawArray:
        return RawArray(np.load(path, mmap_mode="r"), sidecar_wavelengths(path))


class NpzReader:
    suffixes = (".npz",)

    def read(self, path: Path, *, dataset: str | None = None) -> RawArray:
        with np.load(path) as z:
            items = {k: z[k] for k in z.files}
        key = pick_cube_key({k: v.shape for k, v in items.items()}, dataset)
        wl = pick_wavelengths({k: v for k, v in items.items() if k != key})
        return RawArray(items[key], wl, meta={"dataset": key})


register_reader(NpyReader())
register_reader(NpzReader())
