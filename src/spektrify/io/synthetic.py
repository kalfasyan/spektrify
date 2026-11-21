"""Synthetic demo cubes (no file needed).

Both demos share one scene: a leaf with a red edge, two kinds of pill-like discs and a tiny
spectrally unusual target. Each cube carries a label map in ``meta["labels"]`` (``(H, W)``
uint8, 0 = background) and the matching names in ``meta["label_names"]``, so tools such as
the lessons in :mod:`spektrify.learn` know what is where. Spatial preprocessing steps that
change the image size (crop, bin) make the label map stale; users of it check the shape.
"""

from __future__ import annotations

import numpy as np

from spektrify.model import Cube


class _Scene:
    """Reflectance ``(H, W, C)``, wavelengths, coordinates and a growing label map."""

    def __init__(self, height: int, width: int, bands: int) -> None:
        self.wl = np.linspace(450.0, 950.0, bands)
        self.yy, self.xx = np.mgrid[0:height, 0:width].astype(np.float32)
        self.labels = np.zeros((height, width), np.uint8)
        self.names = ["background"]
        self.refl = self._paint()

    def label(self, name: str, mask: np.ndarray) -> None:
        if name not in self.names:
            self.names.append(name)
        self.labels[mask] = self.names.index(name)

    def gauss(self, mu: float, sig: float) -> np.ndarray:
        return np.exp(-0.5 * ((self.wl - mu) / sig) ** 2)

    def _paint(self) -> np.ndarray:
        wl, xx, yy, g = self.wl, self.xx, self.yy, self.gauss
        background = 0.18 + 0.05 * (wl - 450) / 500
        # Green bump, chlorophyll absorption around 675 nm, red edge near 715 nm, NIR plateau.
        leaf = 0.05 + 0.08 * g(550, 35) - 0.035 * g(675, 18)
        leaf = leaf + 0.45 / (1 + np.exp(-(wl - 715) / 12))
        pill_a = 0.70 - 0.25 * g(600, 60)
        pill_b = 0.35 + 0.30 * g(520, 40) + 0.15 * g(880, 50)
        anomaly = 0.30 + 0.35 * g(760, 8)

        abund_bg = 1.0 + 0.15 * np.sin(xx / 40.0) * np.cos(yy / 33.0)
        cube = abund_bg[..., None] * background[None, None, :]

        leaf_mask = (((xx - 80) / 55) ** 2 + ((yy - 95) / 75) ** 2) < 1
        leaf_mask &= ((xx - 80) * 0.6 + (yy - 95)) ** 2 / 4000 + ((xx - 80) / 55) ** 2 < 1.2
        vein = np.exp(-(((xx - 80) + 0.15 * (yy - 95)) ** 2) / 6.0)
        leaf_spec = leaf[None, None, :] * (1.0 - 0.25 * vein[..., None])
        cube = np.where(leaf_mask[..., None], leaf_spec, cube)
        self.label("leaf", leaf_mask)

        for cx, cy, spec, name in (
            (170, 50, pill_a, "pill_a"),
            (215, 70, pill_a, "pill_a"),
            (175, 140, pill_b, "pill_b"),
            (225, 150, pill_b, "pill_b"),
        ):
            r = np.hypot(xx - cx, yy - cy)
            m = r < 17
            shade = (1.0 - 0.35 * (r / 17) ** 2)[..., None]
            cube = np.where(m[..., None], spec[None, None, :] * shade, cube)
            self.label(name, m)

        # A small, spectrally-unusual target (for anomaly detection).
        am = np.hypot(xx - 140, yy - 30) < 3.2
        cube = np.where(am[..., None], anomaly[None, None, :], cube)
        self.label("target", am)
        return cube

    def cube(self, data: np.ndarray, name: str, demo: str, note: str) -> Cube:
        return Cube.from_array(
            data.astype(np.float32),
            self.wl,
            layout="hwc",
            name=name,
            meta={
                "note": note,
                "demo": demo,
                "labels": self.labels,
                "label_names": list(self.names),
            },
        )


def demo_cube(height: int = 192, width: int = 256, bands: int = 96, seed: int = 0) -> Cube:
    """A synthetic VNIR reflectance scene with known objects and planted artifacts.

    Useful to try the viewer without data: it contains a leaf-like object with a red edge,
    pill-like discs, a dead column, a striped band, a hot pixel cluster, a noisy band and a
    NaN patch, so every artifact tool has something to find.
    """
    rng = np.random.default_rng(seed)
    sc = _Scene(height, width, bands)
    wl, xx, yy = sc.wl, sc.xx, sc.yy

    # Illumination falloff (vignetting) and sensor noise.
    vign = 1.0 - 0.25 * (((xx - width / 2) / width) ** 2 + ((yy - height / 2) / height) ** 2)
    cube = sc.refl * vign[..., None]
    snr = 120 * np.exp(-(((wl - 680) / 260) ** 2)) + 8
    cube = cube + rng.normal(0, 1, cube.shape) * (cube.mean() / snr)[None, None, :]

    # Planted artifacts.
    dead = min(37, width - 1)
    cube[:, dead, :] *= 0.05  # dead column
    sc.label("dead_column", xx == dead)
    sb = int(bands * 0.8)
    cube[:, :, sb] += (np.sin(np.arange(width) * 1.3) > 0.6)[None, :] * 0.08  # striping
    nb = int(bands * 0.05)
    cube[:, :, nb] += rng.normal(0, 0.12, (height, width))  # very noisy band
    cube[120:124, 20:24, :] = cube.max() * 1.6  # saturated hot cluster
    sc.label("hot_pixels", (yy >= 120) & (yy < 124) & (xx >= 20) & (xx < 24))
    nan_band = int(bands * 0.6)
    cube[5:12, 230:245, nan_band : nan_band + 3] = np.nan  # dropped packet
    sc.label("nan_patch", (yy >= 5) & (yy < 12) & (xx >= 230) & (xx < 245))

    return sc.cube(cube, "demo (synthetic)", "scene", "synthetic scene with planted artifacts")


DARK_LEVEL = 100.0
"""Dark offset (in counts) of :func:`demo_capture`, so a lesson can subtract it exactly."""


def demo_capture(height: int = 192, width: int = 256, bands: int = 96, seed: int = 0) -> Cube:
    """The demo scene as an uncalibrated camera would record it, in raw counts.

    Raw counts = dark offset + lamp spectrum × sensor response × vignetting × reflectance,
    with shot noise. A white reference tile sits at the bottom right (label ``white_tile``)
    and the bands are slightly misregistered (up to ±2 px), as with a filter wheel or a
    snapshot sensor. Calibration (dark, white, flat field) and band alignment undo it.
    """
    rng = np.random.default_rng(seed)
    sc = _Scene(height, width, bands)
    wl, xx, yy = sc.wl, sc.xx, sc.yy

    tile = (xx >= 0.78 * width) & (xx < 0.97 * width) & (yy >= 0.89 * height)
    tile &= yy < 0.97 * height
    refl = np.where(tile[..., None], 0.95, sc.refl)
    sc.label("white_tile", tile)

    # Halogen-like lamp (black body at 2900 K) times a silicon sensor's response.
    lam = wl * 1e-9
    planck = 1.0 / (lam**5 * (np.exp(1.4388e-2 / (lam * 2900.0)) - 1.0))
    response = np.exp(-0.5 * ((wl - 640) / 190) ** 2)
    lamp = planck / planck.max() * response
    lamp /= lamp.max()
    vign = 1.0 - 0.6 * (((xx - width / 2) / width) ** 2 + ((yy - height / 2) / height) ** 2)
    signal = 3000.0 * refl * lamp[None, None, :] * vign[..., None]

    # Band misregistration: a smooth drift across the spectrum, in whole pixels.
    shifts = np.round(2.0 * np.sin(np.linspace(0.0, 2.0 * np.pi, bands))).astype(int)
    for c, dx in enumerate(shifts):
        signal[:, :, c] = np.roll(signal[:, :, c], (int(dx), int(-dx) // 2), axis=(1, 0))

    noise = rng.normal(0, 1, signal.shape) * (np.sqrt(np.maximum(signal, 0)) * 0.6 + 3.0)
    raw = DARK_LEVEL + signal + noise
    cube = sc.cube(raw, "demo capture (raw counts)", "capture", "synthetic raw capture")
    cube.meta["dark_level"] = DARK_LEVEL
    return cube
