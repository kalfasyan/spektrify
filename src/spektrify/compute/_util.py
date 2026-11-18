"""Small helpers shared by compute backends and the API layer."""

from __future__ import annotations

from typing import Any

import numpy as np


def finite_list(a: Any) -> list[float | None]:
    """Flatten to a JSON-safe list: non-finite values become ``None``."""
    arr = np.asarray(a, dtype=np.float64).ravel()
    return [float(v) if np.isfinite(v) else None for v in arr]
