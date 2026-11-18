"""Rasterising region descriptions (as sent by the UI) to boolean masks."""

from __future__ import annotations

from typing import Any

import numpy as np


def region_mask(body: dict[str, Any], h: int, w: int) -> np.ndarray:
    """Rasterise a ``rect`` / ``ellipse`` / ``poly`` region description to an ``(H, W)`` mask."""
    kind = body.get("kind", "rect")
    mask = np.zeros((h, w), dtype=bool)
    if kind in ("rect", "ellipse"):
        x0, x1 = sorted((float(body["x0"]), float(body["x1"])))
        y0, y1 = sorted((float(body["y0"]), float(body["y1"])))
        xi0, xi1 = max(0, int(np.floor(x0))), min(w, int(np.ceil(x1)))
        yi0, yi1 = max(0, int(np.floor(y0))), min(h, int(np.ceil(y1)))
        if xi1 <= xi0 or yi1 <= yi0:
            return mask
        if kind == "rect":
            mask[yi0:yi1, xi0:xi1] = True
        else:
            yy, xx = np.mgrid[yi0:yi1, xi0:xi1] + 0.5
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            mask[yi0:yi1, xi0:xi1] = ((xx - cx) / max(rx, 1e-6)) ** 2 + (
                (yy - cy) / max(ry, 1e-6)
            ) ** 2 <= 1
        return mask
    if kind == "poly":
        pts = np.asarray(body["points"], dtype=float)
        if pts.shape[0] < 3:
            return mask
        xi0, xi1 = max(0, int(np.floor(pts[:, 0].min()))), min(w, int(np.ceil(pts[:, 0].max())))
        yi0, yi1 = max(0, int(np.floor(pts[:, 1].min()))), min(h, int(np.ceil(pts[:, 1].max())))
        if xi1 <= xi0 or yi1 <= yi0:
            return mask
        yy, xx = np.mgrid[yi0:yi1, xi0:xi1] + 0.5
        inside = np.zeros(xx.shape, dtype=bool)
        px, py = pts[:, 0], pts[:, 1]
        j = len(pts) - 1
        for i in range(len(pts)):  # even-odd ray casting, vectorised over pixels
            cond = (py[i] > yy) != (py[j] > yy)
            with np.errstate(divide="ignore", invalid="ignore"):
                xint = (px[j] - px[i]) * (yy - py[i]) / (py[j] - py[i]) + px[i]
            inside ^= cond & (xx < xint)
            j = i
        mask[yi0:yi1, xi0:xi1] = inside
        return mask
    raise ValueError(f"unknown region kind {kind!r}")
