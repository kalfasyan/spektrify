"""ENVI reader: a text ``.hdr`` header next to a raw binary data file."""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

import numpy as np

from spektrify.io.base import RawArray, register_reader

#: Suffixes a raw ENVI data file may carry (opening one of these finds its ``.hdr``).
DATA_SUFFIXES = ("", ".img", ".raw", ".dat", ".bsq", ".bil", ".bip")

_ENVI_DTYPES = {
    1: np.uint8,
    2: np.int16,
    3: np.int32,
    4: np.float32,
    5: np.float64,
    12: np.uint16,
    13: np.uint32,
    14: np.int64,
    15: np.uint64,
}


def parse_envi_header(text: str) -> dict[str, Any]:
    """Parse an ENVI ``.hdr`` file into a dict of lower-cased keys."""
    if not text.lstrip().upper().startswith("ENVI"):
        raise ValueError("Not an ENVI header (missing 'ENVI' magic)")
    out: dict[str, Any] = {}
    for m in re.finditer(r"^\s*([^=\n]+?)\s*=\s*(\{[^}]*\}|[^\n]*)", text, re.MULTILINE):
        key, val = m.group(1).strip().lower(), m.group(2).strip()
        if val.startswith("{"):
            out[key] = [v.strip() for v in val[1:-1].split(",") if v.strip()]
        else:
            out[key] = val
    return out


class EnviReader:
    """ENVI ``.hdr`` + raw data file (BSQ / BIL / BIP, any byte order)."""

    suffixes = (".hdr",)

    def read(self, path: Path, *, dataset: str | None = None) -> RawArray:
        return _read_envi(path)


def _read_envi(path: Path) -> RawArray:
    hdr = parse_envi_header(path.read_text(errors="replace"))
    samples, lines, bands = int(hdr["samples"]), int(hdr["lines"]), int(hdr["bands"])
    dtype = np.dtype(_ENVI_DTYPES[int(hdr.get("data type", 4))])
    if int(hdr.get("byte order", 0)) == 1:
        dtype = dtype.newbyteorder(">")
    offset = int(hdr.get("header offset", 0))
    interleave = str(hdr.get("interleave", "bsq")).lower()

    data_file = None
    for ext in (*DATA_SUFFIXES, *(s.upper() for s in DATA_SUFFIXES if s)):
        cand = path.with_suffix(ext)
        if cand != path and cand.exists() and cand.is_file():
            data_file = cand
            break
    if data_file is None:
        raise FileNotFoundError(f"No data file found next to {path.name}")

    raw = np.memmap(data_file, dtype=dtype, mode="r", offset=offset)
    n = samples * lines * bands
    raw = raw[:n]
    if interleave == "bip":
        hwc = raw.reshape(lines, samples, bands)
    elif interleave == "bil":
        hwc = raw.reshape(lines, bands, samples).transpose(0, 2, 1)
    else:
        hwc = raw.reshape(bands, lines, samples).transpose(1, 2, 0)

    wl = None
    if "wavelength" in hdr:
        try:
            wl = np.array([float(v) for v in hdr["wavelength"]])
        except ValueError:
            wl = None
    meta: dict[str, Any] = {"interleave": interleave}
    units = str(hdr.get("wavelength units", "")).lower()
    if wl is not None and units.startswith("micro"):
        wl = wl * 1000.0
    if "band names" in hdr:
        meta["band_names"] = hdr["band names"]
    if "data ignore value" in hdr:
        with contextlib.suppress(ValueError):
            meta["ignore_value"] = float(hdr["data ignore value"])
    arr = np.array(hwc, dtype=np.float32)
    if "ignore_value" in meta:
        arr[arr == meta["ignore_value"]] = np.nan
    return RawArray(arr, wl, layout="hwc", meta=meta)


register_reader(EnviReader())
