"""File loading: a registry of format readers plus :func:`load_cube`.

Built-in readers: NumPy (.npy/.npz), HDF5 (.h5/.hdf5, incl. spektro raw mosaics), MATLAB
(.mat), ENVI (.hdr + data) and TIFF. Add a format with :func:`register_reader`.
"""

from __future__ import annotations

from pathlib import Path

from spektrify.io import envi_io, hdf5_io, matlab_io, numpy_io, tiff_io  # noqa: F401  (register)
from spektrify.io.base import RawArray, Reader, reader_for, register_reader, supported_suffixes
from spektrify.io.demosaic import demosaic, demosaic_methods, register_demosaicer
from spektrify.io.envi_io import DATA_SUFFIXES, parse_envi_header
from spektrify.io.synthetic import demo_cube
from spektrify.model import Cube

__all__ = [
    "RawArray",
    "Reader",
    "demo_cube",
    "demosaic",
    "demosaic_methods",
    "load_cube",
    "parse_envi_header",
    "reader_for",
    "register_demosaicer",
    "register_reader",
    "supported_suffixes",
]


def load_cube(
    path: str | Path,
    *,
    dataset: str | None = None,
    layout: str = "auto",
    mosaic: int | None = None,
    demosaic_method: str = "block",
) -> Cube:
    """Load a cube from disk with the reader registered for its suffix.

    ``dataset`` picks an array inside container formats (HDF5 / NPZ / MAT). ``layout``
    overrides the reader's axis-order guess. ``mosaic`` forces demosaicing of a 2-D
    snapshot-mosaic image with that macropixel size, using ``demosaic_method``
    (see :func:`demosaic_methods`).
    """
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in DATA_SUFFIXES and path.with_suffix(".hdr").exists():
        path = path.with_suffix(".hdr")  # opened the ENVI data file instead of its header

    raw = reader_for(path).read(path, dataset=dataset)
    array, meta = raw.array, dict(raw.meta)
    eff_layout = raw.layout if layout == "auto" else layout
    tile = mosaic or raw.mosaic_tile
    if tile and array.ndim == 2:
        array = demosaic(array, int(tile), demosaic_method)
        eff_layout = "hwc"
        meta["demosaiced"] = f"{tile}×{tile} macropixel, {demosaic_method}"

    return Cube.from_array(
        array, raw.wavelengths, layout=eff_layout, name=path.name, source=str(path), meta=meta
    )
