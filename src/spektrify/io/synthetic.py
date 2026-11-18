"""Synthetic demo cube with planted artifacts (no file needed)."""

from __future__ import annotations

import numpy as np

from spektrify.model import Cube


def demo_cube(height: int = 192, width: int = 256, bands: int = 96, seed: int = 0) -> Cube:
    """A synthetic VNIR scene with known objects and planted artifacts.

    Useful to try the viewer without data: it contains a leaf-like object with a red edge,
    pill-like discs, a dead column, a striped band, a hot pixel cluster, a noisy band and a
    NaN patch, so every artifact tool has something to find.
    """
    rng = np.random.default_rng(seed)
    wl = np.linspace(450.0, 950.0, bands)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)

    def gauss(mu: float, sig: float) -> np.ndarray:
        return np.exp(-0.5 * ((wl - mu) / sig) ** 2)

    background = 0.18 + 0.05 * (wl - 450) / 500
    leaf = 0.05 + 0.08 * gauss(550, 30) + 0.45 / (1 + np.exp(-(wl - 715) / 12))
    pill_a = 0.70 - 0.25 * gauss(600, 60)
    pill_b = 0.35 + 0.30 * gauss(520, 40) + 0.15 * gauss(880, 50)
    anomaly = 0.30 + 0.35 * gauss(760, 8)

    abund_bg = 1.0 + 0.15 * np.sin(xx / 40.0) * np.cos(yy / 33.0)
    cube = abund_bg[..., None] * background[None, None, :]

    leaf_mask = (((xx - 80) / 55) ** 2 + ((yy - 95) / 75) ** 2) < 1
    leaf_mask &= ((xx - 80) * 0.6 + (yy - 95)) ** 2 / 4000 + ((xx - 80) / 55) ** 2 < 1.2
    vein = np.exp(-(((xx - 80) + 0.15 * (yy - 95)) ** 2) / 6.0)
    leaf_spec = leaf[None, None, :] * (1.0 - 0.25 * vein[..., None])
    cube = np.where(leaf_mask[..., None], leaf_spec, cube)

    for cx, cy, spec in (
        (170, 50, pill_a),
        (215, 70, pill_a),
        (175, 140, pill_b),
        (225, 150, pill_b),
    ):
        r = np.hypot(xx - cx, yy - cy)
        m = r < 17
        shade = (1.0 - 0.35 * (r / 17) ** 2)[..., None]
        cube = np.where(m[..., None], spec[None, None, :] * shade, cube)

    # A small, spectrally-unusual target (for anomaly detection).
    am = np.hypot(xx - 140, yy - 30) < 3.2
    cube = np.where(am[..., None], anomaly[None, None, :], cube)

    # Illumination falloff (vignetting) and sensor noise.
    vign = 1.0 - 0.25 * (((xx - width / 2) / width) ** 2 + ((yy - height / 2) / height) ** 2)
    cube = cube * vign[..., None]
    snr = 120 * np.exp(-(((wl - 680) / 260) ** 2)) + 8
    cube = cube + rng.normal(0, 1, cube.shape) * (cube.mean() / snr)[None, None, :]

    # Planted artifacts.
    cube[:, min(37, width - 1), :] *= 0.05  # dead column
    sb = int(bands * 0.8)
    cube[:, :, sb] += (np.sin(np.arange(width) * 1.3) > 0.6)[None, :] * 0.08  # striping
    nb = int(bands * 0.05)
    cube[:, :, nb] += rng.normal(0, 0.12, (height, width))  # very noisy band
    cube[120:124, 20:24, :] = cube.max() * 1.6  # saturated hot cluster
    cube[5:12, 230:245, int(bands * 0.6) : int(bands * 0.6) + 3] = np.nan  # dropped packet

    return Cube.from_array(
        cube.astype(np.float32),
        wl,
        layout="hwc",
        name="demo (synthetic)",
        meta={"note": "synthetic scene with planted artifacts"},
    )
