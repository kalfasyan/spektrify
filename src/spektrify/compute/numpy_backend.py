"""NumPy compute backend: band statistics, data-quality metrics, PCA, anomaly detectors,
spectral similarity and band math.

Everything works on a band-major ``(C, H, W)`` float32 array and is NaN-tolerant.
Expensive results are memoised per instance.
"""

from __future__ import annotations

import threading
import warnings
from functools import cached_property
from typing import Any

import numpy as np
from numpy.typing import NDArray

from spektrify.compute import capture, imageops
from spektrify.compute._util import finite_list as _clean
from spektrify.compute.bandmath import safe_eval
from spektrify.model import Cube

F32 = NDArray[np.float32]

_MAX_SAMPLES = 120_000


def _robust_sigma(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


class NumpyAnalyzer:
    """Reference :class:`~spektrify.compute.base.Analyzer`: NumPy, lazily computed and
    memoised per cube."""

    def __init__(self, cube: Cube) -> None:
        self.cube = cube
        self._lock = threading.RLock()
        self._pca_cache: dict[int, dict[str, Any]] = {}
        self._cluster_cache: dict[int, F32] = {}

    # ------------------------------------------------------------------ sampling

    @cached_property
    def finite_mask(self) -> NDArray[np.bool_]:
        """``(H, W)`` mask of pixels whose whole spectrum is finite."""
        return np.all(np.isfinite(self.cube.data), axis=0)

    @cached_property
    def sample_index(self) -> NDArray[np.intp]:
        """Flat indices of a reproducible random subset of fully-finite pixels."""
        idx = np.flatnonzero(self.finite_mask.ravel())
        if idx.size > _MAX_SAMPLES:
            rng = np.random.default_rng(0)
            idx = np.sort(rng.choice(idx, _MAX_SAMPLES, replace=False))
        return idx

    @cached_property
    def samples(self) -> NDArray[np.float64]:
        """``(N, C)`` sample of spectra used to fit statistics."""
        flat = self.cube.data.reshape(self.cube.n_bands, -1)
        return flat[:, self.sample_index].T.astype(np.float64)

    # ------------------------------------------------------------------ band stats

    @cached_property
    def band_stats(self) -> list[dict[str, float]]:
        """Per-band summary statistics and quality indicators."""
        data = self.cube.data
        dtype_max = self.cube.meta.get("dtype_max")
        out = []
        for b in range(self.cube.n_bands):
            band = data[b]
            fin = np.isfinite(band)
            n_fin = int(fin.sum())
            n = band.size
            v = band[fin] if n_fin < n else band.ravel()
            if v.size == 0:
                out.append({"band": b, "valid": 0.0, "nan": float(n - n_fin)})
                continue
            p = np.percentile(v, [0.5, 1, 2, 50, 98, 99, 99.5])
            vmin, vmax = float(v.min()), float(v.max())
            mean, std = float(v.mean()), float(v.std())
            # Noise from horizontal neighbour differences (robust to scene structure).
            d = np.diff(band, axis=1)
            noise = _robust_sigma(d.ravel()[:: max(1, d.size // 400_000)]) / np.sqrt(2)
            sat_level = dtype_max if dtype_max is not None else vmax
            n_max = int(np.count_nonzero(v >= sat_level))
            n_min = int(np.count_nonzero(v <= vmin))
            out.append(
                {
                    "band": b,
                    "min": vmin,
                    "max": vmax,
                    "mean": mean,
                    "std": std,
                    "p005": float(p[0]),
                    "p01": float(p[1]),
                    "p02": float(p[2]),
                    "median": float(p[3]),
                    "p98": float(p[4]),
                    "p99": float(p[5]),
                    "p995": float(p[6]),
                    "noise": float(noise),
                    "snr": float(abs(mean) / noise) if noise > 0 else float("inf"),
                    "nan": float(np.count_nonzero(np.isnan(band))),
                    "inf": float(np.count_nonzero(np.isinf(band))),
                    "zeros": float(np.count_nonzero(v == 0)),
                    # Many pixels tied at the extreme value usually means clipping.
                    "clip_hi": n_max / n if n_max >= 4 else 0.0,
                    "clip_lo": n_min / n if n_min >= 4 else 0.0,
                    "n_at_max": float(n_max),
                }
            )
        return out

    @cached_property
    def global_range(self) -> dict[str, float]:
        s = self.samples
        if s.size == 0:
            return {"p01": 0.0, "p99": 1.0, "min": 0.0, "max": 1.0}
        p = np.percentile(s, [0.5, 1, 99, 99.5])
        return {
            "p005": float(p[0]),
            "p01": float(p[1]),
            "p99": float(p[2]),
            "p995": float(p[3]),
            "min": float(np.nanmin(self.cube.data)),
            "max": float(np.nanmax(self.cube.data)),
        }

    @cached_property
    def mean_spectrum(self) -> NDArray[np.float64]:
        s = self.samples
        return s.mean(0) if s.size else np.zeros(self.cube.n_bands)

    # ------------------------------------------------------------------ quality

    @cached_property
    def correlation(self) -> NDArray[np.float32]:
        """``(C, C)`` Pearson correlation between bands."""
        s = self.samples
        if s.shape[0] < 3:
            return np.eye(self.cube.n_bands, dtype=np.float32)
        sd = s.std(0)
        sd[sd == 0] = 1
        z = (s - s.mean(0)) / sd
        return ((z.T @ z) / s.shape[0]).astype(np.float32)

    @cached_property
    def stripe_profiles(self) -> dict[str, F32]:
        """Per-band column / row line-artifact scores in noise units: ``(C, W)`` / ``(C, H)``.

        For every pixel we take the second difference across the line direction
        (``I[x] - (I[x-1] + I[x+1]) / 2``) and then the *median* along the line. Object edges
        only touch some rows of a column so their median stays near zero, whereas a dead
        detector column or a push-broom stripe shifts every row and stands out sharply.
        """
        data = self.cube.data
        c, h, w = data.shape
        res = {}
        for key, axis in (("columns", 2), ("rows", 1)):
            n_line = w if axis == 2 else h
            if n_line < 3:
                res[key] = np.zeros((c, n_line), dtype=np.float32)
                continue
            # Subsample the direction we take the median over (speed on large cubes).
            along = h if axis == 2 else w
            step = max(1, along // 512)
            sub = data[:, ::step, :] if axis == 2 else data[:, :, ::step]
            mid = np.take(sub, range(1, n_line - 1), axis=axis)
            lo = np.take(sub, range(n_line - 2), axis=axis)
            hi = np.take(sub, range(2, n_line), axis=axis)
            d2 = mid - 0.5 * (lo + hi)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                med = np.nanmedian(d2, axis=1 if axis == 2 else 2)  # (C, n_line-2)
            med = np.nan_to_num(med)
            scale = np.array(
                [_robust_sigma(d2[b].ravel()[:: max(1, d2[b].size // 200_000)]) for b in range(c)]
            )
            # Median of n noisy samples has ~1.25/sqrt(n) of their spread.
            scale = scale * 1.2533 / np.sqrt(max(1, d2.shape[1 if axis == 2 else 2]))
            scale[~np.isfinite(scale) | (scale <= 0)] = 1.0
            out = np.zeros((c, n_line), dtype=np.float32)
            out[:, 1:-1] = med / scale[:, None]
            res[key] = out
        return res

    @cached_property
    def quality(self) -> dict[str, Any]:
        """Per-band quality metrics plus human-readable flags for suspicious bands."""
        stats = self.band_stats
        c = self.cube.n_bands
        corr = self.correlation
        nb = np.ones(c)
        for b in range(c):
            ns = [corr[b, j] for j in (b - 1, b + 1) if 0 <= j < c]
            nb[b] = float(np.nanmax(ns)) if ns else 1.0
        stripes = self.stripe_profiles
        # Lines that are off in (nearly) every band are sensor-level defects; report them
        # separately so they don't make every band look striped.
        bad_cols = _line_defects(np.median(np.abs(stripes["columns"]), axis=0))
        bad_rows = _line_defects(np.median(np.abs(stripes["rows"]), axis=0))
        keep = np.ones(self.cube.width, dtype=bool)
        for x in bad_cols:
            keep[max(0, x - 1) : x + 2] = False
        cols = np.abs(stripes["columns"][:, keep]) if keep.any() else np.zeros((c, 1))
        stripe_score = np.percentile(cols, 99.5, axis=1)
        snr = np.array([s.get("snr", np.nan) for s in stats], dtype=np.float64)
        n_pix = self.cube.height * self.cube.width
        bad_frac = np.array([(s.get("nan", 0) + s.get("inf", 0)) / n_pix for s in stats])
        clip = np.array([s.get("clip_hi", 0.0) for s in stats])

        flags: list[dict[str, Any]] = []
        sat_everywhere = c > 1 and float(np.mean(clip > 0)) > 0.5
        finite_snr = snr[np.isfinite(snr)]
        med_snr = float(np.median(finite_snr)) if finite_snr.size else float("nan")
        med_stripe = float(np.median(stripe_score)) if c else 0.0
        for b in range(c):
            reasons = []
            if np.isfinite(snr[b]) and np.isfinite(med_snr) and snr[b] < med_snr / 4:
                reasons.append(f"low SNR ({snr[b]:.1f} vs median {med_snr:.1f})")
            if c > 2 and nb[b] < 0.8:
                reasons.append(f"decorrelated from neighbours (r={nb[b]:.2f})")
            if bad_frac[b] > 0:
                reasons.append(f"{bad_frac[b] * 100:.2f}% NaN/Inf")
            if clip[b] > 0 and not sat_everywhere:
                n_sat = int(stats[b].get("n_at_max", 0))
                reasons.append(f"{n_sat} px pinned at max ({clip[b] * 100:.2g}%, saturation?)")
            if stripe_score[b] > max(10.0, 4 * med_stripe):
                reasons.append(f"column striping ({stripe_score[b]:.0f}σ)")
            if reasons:
                flags.append({"band": b, "reasons": reasons})

        issues: list[str] = []
        if bad_cols:
            issues.append(
                f"{len(bad_cols)} column defect(s) across bands: x = {_fmt_list(bad_cols)}"
            )
        if bad_rows:
            issues.append(f"{len(bad_rows)} row defect(s) across bands: y = {_fmt_list(bad_rows)}")
        n_invalid = int((~self.finite_mask).sum())
        if n_invalid:
            issues.append(f"{n_invalid} pixel(s) with NaN/Inf in at least one band")
        if sat_everywhere:
            n_sat = int(np.median([s.get("n_at_max", 0) for s in stats]))
            issues.append(
                f"~{n_sat} px pinned at the maximum value in {int((clip > 0).sum())}/{c} bands "
                "(saturation or clipping)"
            )
        if flags:
            issues.append(f"{len(flags)} band(s) flagged")

        return {
            "issues": issues,
            "snr": _clean(snr),
            "neighbor_corr": _clean(nb),
            "stripe": _clean(stripe_score),
            "bad_frac": _clean(bad_frac),
            "clip": _clean(clip),
            "flags": flags,
            "bad_columns": bad_cols[:200],
            "bad_rows": bad_rows[:200],
            "invalid_pixels": int((~self.finite_mask).sum()),
        }

    # ------------------------------------------------------------------ PCA family

    def pca(self, k: int = 10) -> dict[str, Any]:
        """Principal components fitted on a pixel sample (k clipped to the band count)."""
        k = int(max(1, min(k, self.cube.n_bands)))
        with self._lock:
            if k in self._pca_cache:
                return self._pca_cache[k]
            s = self.samples
            mean = s.mean(0) if s.size else np.zeros(self.cube.n_bands)
            if s.shape[0] < 2:
                comps = np.eye(self.cube.n_bands)[:k]
                ev = np.ones(k)
                total = float(k)
            else:
                cov = np.cov(s - mean, rowvar=False)
                cov = np.atleast_2d(cov)
                w, v = np.linalg.eigh(cov)
                order = np.argsort(w)[::-1]
                w, v = w[order], v[:, order]
                # Deterministic sign: largest loading positive.
                signs = np.sign(v[np.argmax(np.abs(v), axis=0), np.arange(v.shape[1])])
                v = v * np.where(signs == 0, 1, signs)
                comps, ev, total = v[:, :k].T, np.maximum(w[:k], 0), float(np.maximum(w, 0).sum())
            res = {
                "mean": mean,
                "components": comps,  # (k, C)
                "eigenvalues": ev,
                "explained": (ev / total if total > 0 else ev * 0).tolist(),
            }
            self._pca_cache[k] = res
            return res

    def _flat_filled(self) -> NDArray[np.float32]:
        """``(C, H*W)`` data with non-finite values replaced by the band mean."""
        flat = self.cube.data.reshape(self.cube.n_bands, -1)
        if self.finite_mask.all():
            return flat
        filled = flat.copy()
        bad = ~np.isfinite(filled)
        filled[bad] = np.take(self.mean_spectrum.astype(np.float32), np.nonzero(bad)[0])
        return filled

    def project(self, k: int = 3, offset: int = 0) -> F32:
        """Component score maps ``(k, H, W)`` starting at component ``offset``."""
        p = self.pca(offset + k)
        comps = p["components"][offset : offset + k].astype(np.float32)
        flat = self._flat_filled()
        scores = comps @ flat - (comps @ p["mean"].astype(np.float32))[:, None]
        scores = scores.reshape(-1, self.cube.height, self.cube.width)
        scores[:, ~self.finite_mask] = np.nan
        return scores.astype(np.float32)

    def rx(self, k: int | None = None) -> F32:
        """Global Reed–Xiaoli anomaly score (Mahalanobis distance in PCA space)."""
        c = self.cube.n_bands
        k = int(min(k or min(c, 30), c))
        p = self.pca(k)
        ev = np.maximum(
            np.asarray(p["eigenvalues"]), 1e-12 * max(1e-30, float(np.max(p["eigenvalues"])))
        )
        scores = self.project(k)
        d2 = np.zeros(scores.shape[1:], dtype=np.float64)
        for i in range(k):
            d2 += scores[i].astype(np.float64) ** 2 / ev[i]
        out = np.sqrt(d2).astype(np.float32)
        out[~self.finite_mask] = np.nan
        return out

    def pca_residual(self, k: int = 3) -> F32:
        """Reconstruction error after projecting onto the top-``k`` components.

        Pixels the dominant spectral subspace can't explain (rare materials, glints,
        sensor glitches) light up.
        """
        k = int(max(1, min(k, self.cube.n_bands)))
        p = self.pca(k)
        comps = p["components"].astype(np.float32)
        mean = p["mean"].astype(np.float32)
        flat = self._flat_filled() - mean[:, None]
        recon = comps.T @ (comps @ flat)
        err = np.sqrt(np.sum((flat - recon) ** 2, axis=0)).reshape(
            self.cube.height, self.cube.width
        )
        err[~self.finite_mask] = np.nan
        return err.astype(np.float32)

    def spectral_angle(self, reference: np.ndarray | None = None) -> F32:
        """Spectral angle (radians) between every pixel and ``reference`` (default: scene mean)."""
        ref = self.mean_spectrum if reference is None else np.asarray(reference, dtype=np.float64)
        ref = ref.astype(np.float32)
        flat = self._flat_filled()
        dot = ref @ flat
        norm = np.sqrt(np.sum(flat.astype(np.float32) ** 2, axis=0)) * float(np.linalg.norm(ref))
        with np.errstate(all="ignore"):
            cos = np.clip(dot / norm, -1, 1)
        ang = np.arccos(cos).reshape(self.cube.height, self.cube.width).astype(np.float32)
        ang[~self.finite_mask] = np.nan
        return ang

    def spectral_gradient(self) -> F32:
        """Mean absolute band-to-band difference per pixel: highlights spiky spectra."""
        d = np.abs(np.diff(self.cube.data, axis=0))
        with np.errstate(all="ignore"):
            return np.nanmean(d, axis=0).astype(np.float32) if d.size else self.cube.data[0] * 0

    def summary_map(self, kind: str) -> F32:
        with np.errstate(all="ignore"):
            if kind == "mean":
                return np.nanmean(self.cube.data, axis=0).astype(np.float32)
            if kind == "std":
                return np.nanstd(self.cube.data, axis=0).astype(np.float32)
            if kind == "max":
                return np.nanmax(self.cube.data, axis=0).astype(np.float32)
            if kind == "argmax":
                filled = np.where(np.isfinite(self.cube.data), self.cube.data, -np.inf)
                idx = np.argmax(filled, axis=0)
                return self.cube.axis[idx].astype(np.float32)
            if kind == "invalid":
                return (~np.isfinite(self.cube.data)).sum(0).astype(np.float32)
        raise ValueError(f"Unknown summary {kind!r}")

    # ------------------------------------------------------------------ sampling helpers

    def scatter_points(self, n: int = 40_000, k: int = 3) -> dict[str, Any]:
        """PCA scores of a pixel subset for the 3-D point cloud."""
        idx = self.sample_index
        if idx.size > n:
            idx = idx[np.linspace(0, idx.size - 1, n).astype(int)]
        p = self.pca(max(k, 3))
        comps = p["components"][:3]
        flat = self.cube.data.reshape(self.cube.n_bands, -1)[:, idx].astype(np.float64)
        scores = comps @ (flat - p["mean"][:, None])
        return {
            "index": idx,
            "scores": scores.T.astype(np.float32),
            "explained": p["explained"][:3],
        }

    def line_profile(self, x0: float, y0: float, x1: float, y1: float) -> F32:
        """Spectra sampled (nearest pixel) along a segment: ``(N, C)``."""
        n = int(max(2, np.ceil(np.hypot(x1 - x0, y1 - y0)) + 1))
        xs = np.clip(np.round(np.linspace(x0, x1, n)).astype(int), 0, self.cube.width - 1)
        ys = np.clip(np.round(np.linspace(y0, y1, n)).astype(int), 0, self.cube.height - 1)
        return np.ascontiguousarray(self.cube.data[:, ys, xs].T)

    def region_stats(self, mask: NDArray[np.bool_]) -> dict[str, Any]:
        sub = self.cube.data[:, mask]  # (C, N)
        n = int(mask.sum())
        if n == 0:
            return {"n": 0}
        with np.errstate(all="ignore"):
            return {
                "n": n,
                "mean": _clean(np.nanmean(sub, axis=1)),
                "std": _clean(np.nanstd(sub, axis=1)),
                "min": _clean(np.nanmin(sub, axis=1)),
                "max": _clean(np.nanmax(sub, axis=1)),
                "p05": _clean(np.nanpercentile(sub, 5, axis=1)),
                "p95": _clean(np.nanpercentile(sub, 95, axis=1)),
            }

    def volume(
        self, max_xy: int = 192, max_c: int = 256
    ) -> tuple[NDArray[np.uint8], dict[str, Any]]:
        """Downsampled cube normalised to ``uint8`` for GPU volume rendering.

        Returned array is ``(C', H', W')`` (z = spectral axis), C-contiguous.
        """
        c, h, w = self.cube.data.shape
        sy = max(1, int(np.ceil(h / max_xy)))
        sx = max(1, int(np.ceil(w / max_xy)))
        sc = max(1, int(np.ceil(c / max_c)))
        hh, ww, cc = h // sy, w // sx, c // sc
        v = self.cube.data[: cc * sc, : hh * sy, : ww * sx]
        v = v.reshape(cc, sc, hh, sy, ww, sx)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            v = np.nanmean(v, axis=(1, 3, 5))
        g = self.global_range
        lo, hi = g["p005"], g["p995"]
        u8 = np.clip((np.nan_to_num(v, nan=lo) - lo) / max(hi - lo, 1e-12) * 255, 0, 255)
        return np.ascontiguousarray(u8.astype(np.uint8)), {
            "shape": [cc, hh, ww],
            "step": [sc, sy, sx],
            "lo": lo,
            "hi": hi,
        }

    def thumbnails(self, max_side: int = 128) -> tuple[F32, dict[str, Any]]:
        """Block-averaged thumbnails for every band: ``(C, th, tw)`` float32."""
        c, h, w = self.cube.data.shape
        s = max(1, int(np.ceil(max(h, w) / max_side)))
        th, tw = h // s, w // s
        if th == 0 or tw == 0:
            s, th, tw = 1, h, w
        v = self.cube.data[:, : th * s, : tw * s].reshape(c, th, s, tw, s)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            t = np.nanmean(v, axis=(2, 4)).astype(np.float32) if s > 1 else v[:, :, 0, :, 0].copy()
        return np.ascontiguousarray(t), {"bands": c, "height": th, "width": tw, "step": s}

    # ------------------------------------------------------------------ clustering

    def clusters(self, k: int = 4) -> F32:
        """k-means cluster map ``(H, W)``: pixels numbered 1..k by spectrum, darkest cluster
        first. Fitted on a sample of pixels, then every pixel goes to its nearest centre."""
        k = int(min(max(int(k), 2), 12))
        with self._lock:
            if k not in self._cluster_cache:
                samples = self.samples[:: max(1, len(self.samples) // 20_000)]
                centres = imageops.kmeans(samples, k)
                flat = self._flat_filled().T
                out = (imageops.nearest(flat, centres) + 1).astype(np.float32)
                out = out.reshape(self.cube.height, self.cube.width)
                out[~self.finite_mask] = np.nan
                self._cluster_cache[k] = out
            return self._cluster_cache[k]

    # ------------------------------------------------------------------ band math

    def band_math(self, expr: str) -> F32:
        """Evaluate a safe arithmetic expression over bands.

        Names: ``b[i]`` (band by index), ``nm(λ)`` (band nearest to wavelength λ),
        ``mean``/``std`` (per-pixel across bands), numpy functions ``sqrt log exp abs
        clip minimum maximum where``, the image functions of
        :mod:`spektrify.compute.imageops` (``gauss(nm(670), 2)``, ``grad``, ``otsu`` …), the
        capture simulations of :mod:`spektrify.compute.capture` (``expose``, ``bayer`` …),
        ``kmeans(k)`` (cluster map of the whole cube), ``mosaic(t)`` (a snapshot-mosaic
        frame), ``x`` / ``y`` (pixel column / row, for test patterns such as
        ``cos(((x - 128)**2 + (y - 96)**2) / 150)``), ``sin`` ``cos`` and arithmetic /
        comparison operators.
        Example: ``(nm(800) - nm(670)) / (nm(800) + nm(670))``.
        """
        cube = self.cube

        class _Bands:
            def __getitem__(self, i: int) -> np.ndarray:
                i = int(i)
                if not -cube.n_bands <= i < cube.n_bands:
                    raise IndexError(f"band {i} out of range 0..{cube.n_bands - 1}")
                return cube.data[i].astype(np.float32)

        def nm(lam: float) -> np.ndarray:
            return cube.data[int(np.argmin(np.abs(cube.axis - float(lam))))]

        def band_range(a: float, b: float) -> np.ndarray:
            ax = cube.axis
            sel = (ax >= min(a, b)) & (ax <= max(a, b))
            if not sel.any():
                sel[int(np.argmin(np.abs(ax - (a + b) / 2)))] = True
            with np.errstate(all="ignore"):
                return np.nanmean(cube.data[sel], axis=0)

        env: dict[str, Any] = {
            "b": _Bands(),
            "nm": nm,
            "avg": band_range,
            "mean": self.summary_map("mean"),
            "std": self.summary_map("std"),
            "sqrt": np.sqrt,
            "log": np.log,
            "log10": np.log10,
            "exp": np.exp,
            "abs": np.abs,
            "clip": np.clip,
            "minimum": np.minimum,
            "maximum": np.maximum,
            "where": np.where,
            "pi": np.pi,
            "sin": np.sin,
            "cos": np.cos,
            "x": np.arange(cube.width, dtype=np.float32)[None, :],
            "y": np.arange(cube.height, dtype=np.float32)[:, None],
            "kmeans": self.clusters,
            "mosaic": lambda t=4: capture.mosaic_frame(cube.data, t),
            **imageops.BANDMATH_FUNCTIONS,
            **capture.BANDMATH_FUNCTIONS,
        }
        with np.errstate(all="ignore"):
            out = safe_eval(expr, env)
        out = np.asarray(out, dtype=np.float32)
        if out.shape != (cube.height, cube.width):
            out = np.broadcast_to(out, (cube.height, cube.width)).astype(np.float32)
        return np.ascontiguousarray(out)


def _line_defects(dev: np.ndarray, thresh: float = 8.0) -> list[int]:
    """Indices where ``dev`` exceeds ``thresh`` and is a local maximum (drops the half-height
    echoes a second difference leaves on both sides of a defect)."""
    if dev.size < 3:
        return []
    left = np.concatenate([[-np.inf], dev[:-1]])
    right = np.concatenate([dev[1:], [-np.inf]])
    return np.flatnonzero((dev > thresh) & (dev >= left) & (dev >= right)).tolist()[:200]


def _fmt_list(v: list[int], n: int = 8) -> str:
    return ", ".join(map(str, v[:n])) + (" …" if len(v) > n else "")
