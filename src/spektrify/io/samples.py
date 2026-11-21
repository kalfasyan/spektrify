"""Real sample images that ship with the package (small, and free to redistribute).

``photo``: the NASA portrait of astronaut Eileen Collins (1997), as distributed with
scikit-image (``skimage.data.astronaut``). NASA images carry no copyright and are in the
public domain. Stored here at 256 × 256 (2 × 2 average of the 512 × 512 original), as 8-bit
sRGB in ``data/astronaut.npz``.
"""

from __future__ import annotations

from importlib.resources import files

import numpy as np

from spektrify.model import Cube

PHOTO_WAVELENGTHS = (460.0, 535.0, 600.0)
"""Nominal peak sensitivities of a consumer camera's blue, green and red filters (nm). The
filters are broad (about 100 nm wide), so these only place the channels on the axis."""


def srgb_to_linear(v: np.ndarray) -> np.ndarray:
    """Undo the sRGB encoding (values 0..1): back to numbers proportional to the light."""
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def demo_photo() -> Cube:
    """A real colour photo as a 3-band cube (blue, green, red), in linear light (0..1)."""
    with files("spektrify.io").joinpath("data").joinpath("astronaut.npz").open("rb") as f:
        rgb = np.load(f)["rgb"]
    lin = srgb_to_linear(rgb[..., ::-1].astype(np.float32) / 255.0)
    h, w = lin.shape[:2]
    return Cube.from_array(
        lin.astype(np.float32),
        np.array(PHOTO_WAVELENGTHS),
        layout="hwc",
        name="photo (NASA, public domain)",
        meta={
            "note": "Eileen Collins, NASA portrait (public domain), via scikit-image",
            "demo": "photo",
            "labels": np.zeros((h, w), np.uint8),
            "label_names": ["background"],
        },
    )
