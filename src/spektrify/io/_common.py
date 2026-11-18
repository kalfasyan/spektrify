"""Helpers shared by the format readers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

WAVELENGTH_KEYS = (
    "wavelengths",
    "wavelength",
    "central_wavelengths",
    "wl",
    "wls",
    "lambda",
    "lambdas",
    "bands",
    "band_centers",
)


def sidecar_wavelengths(path: Path) -> np.ndarray | None:
    for cand in (
        path.with_name(path.stem + "_wavelengths.npy"),
        path.with_name(path.stem + ".wavelengths.npy"),
        path.with_name("wavelengths.npy"),
    ):
        if cand.exists():
            return np.load(cand).astype(float).ravel()
    for cand in (path.with_name(path.stem + "_wavelengths.txt"), path.with_name("wavelengths.txt")):
        if cand.exists():
            return np.loadtxt(cand, dtype=float).ravel()
    return None


def pick_wavelengths(items: dict[str, np.ndarray]) -> np.ndarray | None:
    lowered = {k.lower().split("/")[-1]: v for k, v in items.items()}
    for key in WAVELENGTH_KEYS:
        v = lowered.get(key)
        if v is not None and np.asarray(v).ndim <= 2 and np.asarray(v).size > 1:
            return np.asarray(v, dtype=float).ravel()
    return None


def pick_cube_key(shapes: dict[str, tuple[int, ...]], dataset: str | None) -> str:
    if dataset is not None:
        if dataset not in shapes:
            raise KeyError(f"Dataset {dataset!r} not found. Available: {sorted(shapes)}")
        return dataset
    for preferred in ("cube", "data", "hsi", "image", "img", "x", "reflectance", "radiance"):
        for k, shp in shapes.items():
            if k.lower().split("/")[-1] == preferred and len(shp) >= 2:
                return k
    candidates = [k for k, s in shapes.items() if len(s) == 3] or [
        k for k, s in shapes.items() if len(s) == 2 and min(s) > 1
    ]
    if not candidates:
        raise ValueError(f"No 2-D or 3-D array found. Arrays: {dict(shapes.items())}")
    return max(candidates, key=lambda k: int(np.prod(shapes[k])))
