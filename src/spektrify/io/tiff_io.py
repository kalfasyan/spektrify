"""Multi-band TIFF reader (tifffile if installed, Pillow otherwise)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from spektrify.io._common import sidecar_wavelengths
from spektrify.io.base import RawArray, register_reader


class TiffReader:
    suffixes: tuple[str, ...] = (".tif", ".tiff")

    def read(self, path: Path, *, dataset: str | None = None) -> RawArray:
        try:
            import tifffile

            arr = tifffile.imread(path)
        except ImportError:
            from PIL import Image, ImageSequence  # ty: ignore[import-not-found]

            with Image.open(path) as im:
                frames = [np.asarray(p) for p in ImageSequence.Iterator(im)]
            arr = np.stack(frames, 0) if len(frames) > 1 else frames[0]
        return RawArray(arr, sidecar_wavelengths(path))


register_reader(TiffReader())
