"""Compute backends behind the viewer (see :class:`Analyzer`)."""

from __future__ import annotations

from collections.abc import Callable

from spektrify.compute.base import Analyzer
from spektrify.compute.numpy_backend import NumpyAnalyzer
from spektrify.compute.regions import region_mask
from spektrify.model import Cube

__all__ = ["Analyzer", "NumpyAnalyzer", "create_analyzer", "region_mask", "register_backend"]

_BACKENDS: dict[str, Callable[[Cube], Analyzer]] = {"numpy": NumpyAnalyzer}


def register_backend(name: str, factory: Callable[[Cube], Analyzer]) -> None:
    """Make an alternative implementation selectable by name."""
    _BACKENDS[name] = factory


def create_analyzer(cube: Cube, backend: str = "numpy") -> Analyzer:
    try:
        return _BACKENDS[backend](cube)
    except KeyError:
        raise ValueError(f"Unknown compute backend {backend!r}; have {sorted(_BACKENDS)}") from None
