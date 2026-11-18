"""Strict JSON encoding shared by the HTTP API and the CLI (NaN / Inf become ``null``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from spektrify.compute._util import finite_list


def _default(o: Any) -> Any:
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.ndarray):
        return finite_list(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def _finite(obj: Any) -> Any:
    """Replace non-finite Python floats (which ``default`` never sees) with ``None``."""
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


def dumps(obj: Any, *, indent: int | None = None) -> str:
    return json.dumps(_finite(obj), allow_nan=False, default=_default, indent=indent)
