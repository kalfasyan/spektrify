"""Reader interface and registry.

A *reader* turns a file into a :class:`RawArray` (a numpy array plus optional wavelengths and
metadata). Readers know nothing about the viewer: adding a format is one small module that
calls :func:`register_reader`, and a faster implementation (e.g. a Rust extension) can
replace any reader by registering for the same suffixes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np


@dataclass
class RawArray:
    """What a reader returns, before it becomes a :class:`~spektrify.model.Cube`.

    ``layout`` is ``"auto"``, ``"hwc"`` or ``"chw"``. ``mosaic_tile`` asks the loader to
    demosaic a 2-D snapshot mosaic with that macropixel size.
    """

    array: np.ndarray
    wavelengths: np.ndarray | None = None
    layout: str = "auto"
    meta: dict[str, Any] = field(default_factory=dict)
    mosaic_tile: int | None = None


@runtime_checkable
class Reader(Protocol):
    """A file-format reader."""

    #: Lower-case file suffixes this reader handles, e.g. ``(".h5", ".hdf5")``.
    suffixes: tuple[str, ...]

    def read(self, path: Path, *, dataset: str | None = None) -> RawArray: ...


_REGISTRY: dict[str, Reader] = {}


def register_reader(reader: Reader) -> Reader:
    """Register ``reader`` for its suffixes (later registrations win)."""
    for s in reader.suffixes:
        _REGISTRY[s.lower()] = reader
    return reader


def reader_for(path: Path) -> Reader:
    reader = _REGISTRY.get(path.suffix.lower())
    if reader is None:
        raise ValueError(
            f"Unsupported file type {path.suffix!r}. Supported: {', '.join(supported_suffixes())}"
        )
    return reader


def supported_suffixes() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))
