"""The viewer's HTTP API as plain functions, independent of any web framework.

Each route takes ``(session, request)`` and returns a :class:`Json` or :class:`Binary`
response. :mod:`spektrify.server.http` adapts them to the stdlib server; another
transport (FastAPI, aiohttp, a Tauri/Rust shell, tests) can call :func:`dispatch` directly.
The wire contract is documented in ``docs/architecture.md``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from spektrify.compute import region_mask
from spektrify.compute._util import finite_list
from spektrify.io import load_cube, supported_suffixes
from spektrify.model import Cube
from spektrify.server.session import Session

MAX_UPLOAD = 8 * 1024**3


# --------------------------------------------------------------------------- types


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Request:
    params: dict[str, list[str]] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    stream: BinaryIO | None = None  # raw body, for uploads
    length: int = 0

    def get(self, key: str, default: Any = ..., cast: Callable[[str], Any] = str) -> Any:
        if key not in self.params:
            if default is ...:
                raise ApiError(400, f"missing query parameter {key!r}")
            return default
        try:
            return cast(self.params[key][0])
        except ValueError as e:
            raise ApiError(400, f"bad value for {key!r}") from e


@dataclass
class Json:
    obj: Any
    status: int = 200


@dataclass
class Binary:
    """A little-endian array; ``meta`` travels as JSON in the ``X-Meta`` header."""

    array: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)


Route = Callable[[Session, Request], Json | Binary]
ROUTES: dict[tuple[str, str], Route] = {}


def route(method: str, name: str) -> Callable[[Route], Route]:
    def deco(fn: Route) -> Route:
        ROUTES[(method, name)] = fn
        return fn

    return deco


def dispatch(session: Session, method: str, name: str, req: Request) -> Json | Binary:
    fn = ROUTES.get((method, name))
    if fn is None:
        raise ApiError(404, f"no endpoint {method} /api/{name}")
    return fn(session, req)


def _f(v: Any) -> Any:
    return None if isinstance(v, float) and not np.isfinite(v) else v


# --------------------------------------------------------------------------- cube & data


@route("GET", "meta")
def meta(s: Session, r: Request) -> Json:
    if s.cube is None:
        return Json({"loaded": False, "recent": s.recent})
    cube, an = s.require()
    return Json(
        {
            "loaded": True,
            "generation": s.generation,
            "name": cube.name,
            "source": cube.source,
            "bands": cube.n_bands,
            "height": cube.height,
            "width": cube.width,
            "wavelengths": None if cube.wavelengths is None else cube.wavelengths.tolist(),
            "axis": cube.axis.tolist(),
            "unit": cube.axis_unit,
            "meta": cube.json_meta(),
            "band_names": cube.meta.get("band_names"),
            "global": an.global_range,
            "band_stats": [{k: _f(v) for k, v in st.items()} for st in an.band_stats],
            "mean_spectrum": finite_list(an.mean_spectrum),
            "invalid_pixels": int((~an.finite_mask).sum()),
            "recent": s.recent,
        }
    )


@route("GET", "generation")
def generation(s: Session, r: Request) -> Json:
    return Json({"generation": s.generation})


@route("GET", "band")
def band(s: Session, r: Request) -> Binary:
    cube, _ = s.require()
    i = r.get("i", cast=int)
    if not 0 <= i < cube.n_bands:
        raise ApiError(400, f"band {i} out of range")
    return Binary(cube.data[i], {"band": i})


@route("GET", "thumbs")
def thumbs(s: Session, r: Request) -> Binary:
    _, an = s.require()
    side = r.get("side", 128, int)
    arr, m = s.cached(f"thumbs:{side}", lambda: an.thumbnails(side))
    return Binary(arr, m)


@route("GET", "spectrum")
def spectrum(s: Session, r: Request) -> Json:
    cube, _ = s.require()
    x, y = r.get("x", cast=int), r.get("y", cast=int)
    if not (0 <= x < cube.width and 0 <= y < cube.height):
        raise ApiError(400, "pixel outside the image")
    return Json({"x": x, "y": y, "values": finite_list(cube.data[:, y, x])})


@route("POST", "region")
def region(s: Session, r: Request) -> Json:
    cube, an = s.require()
    return Json(an.region_stats(region_mask(r.body, cube.height, cube.width)))


@route("GET", "slice")
def slice_(s: Session, r: Request) -> Binary:
    """A spectral cross-section: ``axis=row`` → (C, W) at row ``i``; ``col`` → (C, H)."""
    cube, _ = s.require()
    axis, i = r.get("axis", "row"), r.get("i", cast=int)
    if axis == "row":
        i = int(np.clip(i, 0, cube.height - 1))
        arr = cube.data[:, i, :]
    elif axis == "col":
        i = int(np.clip(i, 0, cube.width - 1))
        arr = cube.data[:, :, i]
    else:
        raise ApiError(400, "axis must be row or col")
    return Binary(np.ascontiguousarray(arr), {"axis": axis, "index": i})


@route("GET", "line")
def line(s: Session, r: Request) -> Binary:
    _, an = s.require()
    return Binary(an.line_profile(*(r.get(k, cast=float) for k in ("x0", "y0", "x1", "y1"))))


# --------------------------------------------------------------------------- products


def _product(s: Session, r: Request) -> Binary:
    _, an = s.require()
    kind = r.get("kind")
    k, offset = r.get("k", 3, int), r.get("offset", 0, int)
    meta: dict[str, Any] = {"kind": kind}
    if kind == "pca":
        arr = s.cached(f"pca:{k}:{offset}", lambda: an.project(k, offset))
        meta["explained"] = an.pca(offset + k)["explained"][offset : offset + k]
    elif kind == "rx":
        arr = s.cached(f"rx:{k}", lambda: an.rx(k if k > 3 else None))
    elif kind == "residual":
        arr = s.cached(f"residual:{k}", lambda: an.pca_residual(k))
    elif kind == "sam":
        ref = r.body.get("reference")
        arr = an.spectral_angle(None if ref is None else np.asarray(ref, dtype=float))
    elif kind == "gradient":
        arr = s.cached("gradient", an.spectral_gradient)
    elif kind in ("mean", "std", "max", "argmax", "invalid"):
        arr = s.cached(kind, lambda: an.summary_map(kind))
    elif kind == "math":
        expr = r.body.get("expr") or r.get("expr")
        arr = an.band_math(expr)
        meta["expr"] = expr
    else:
        raise ApiError(400, f"unknown product {kind!r}")
    arr = np.asarray(arr, dtype=np.float32)
    return Binary(arr[None] if arr.ndim == 2 else arr, meta)


ROUTES[("GET", "product")] = _product
ROUTES[("POST", "product")] = _product


# --------------------------------------------------------------------------- quality & 3-D


@route("GET", "quality")
def quality(s: Session, r: Request) -> Json:
    _, an = s.require()
    return Json(an.quality)


@route("GET", "correlation")
def correlation(s: Session, r: Request) -> Binary:
    _, an = s.require()
    return Binary(an.correlation)


@route("GET", "stripes")
def stripes(s: Session, r: Request) -> Binary:
    _, an = s.require()
    which = r.get("which", "columns")
    if which not in ("columns", "rows"):
        raise ApiError(400, "which must be columns or rows")
    return Binary(an.stripe_profiles[which], {"which": which})


@route("GET", "volume")
def volume(s: Session, r: Request) -> Binary:
    _, an = s.require()
    mx = r.get("max", 192, int)
    arr, m = s.cached(f"volume:{mx}", lambda: an.volume(max_xy=mx))
    return Binary(arr, m)


@route("GET", "scatter")
def scatter(s: Session, r: Request) -> Binary:
    """PCA scores of a pixel subset: ``n×3`` float32 bit-cast to uint32, then ``n`` indices."""
    _, an = s.require()
    res = an.scatter_points(r.get("n", 40000, int))
    idx = res["index"].astype(np.uint32)
    packed = np.concatenate([res["scores"].astype(np.float32).ravel().view(np.uint32), idx])
    return Binary(packed, {"n": int(idx.size), "explained": res["explained"]})


# --------------------------------------------------------------------------- files


@route("GET", "browse")
def browse(s: Session, r: Request) -> Json:
    raw = r.get("dir", "")
    base = Path(raw).expanduser() if raw else s.default_dir()
    if not base.is_dir():
        base = base.parent
    suffixes = supported_suffixes()
    entries = []
    try:
        for p in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if p.name.startswith("."):
                continue
            if p.is_dir():
                entries.append({"name": p.name, "path": str(p), "dir": True})
            elif p.suffix.lower() in suffixes:
                entries.append(
                    {"name": p.name, "path": str(p), "dir": False, "size": p.stat().st_size}
                )
    except PermissionError:
        pass
    base = base.resolve()
    return Json(
        {
            "dir": str(base),
            "parent": str(base.parent),
            "entries": entries[:2000],
            "recent": s.recent,
        }
    )


@route("POST", "open")
def open_(s: Session, r: Request) -> Json:
    path = r.body.get("path")
    if not path:
        raise ApiError(400, "path required")
    t0 = time.perf_counter()
    cube = load_cube(
        path,
        dataset=r.body.get("dataset") or None,
        layout=r.body.get("layout") or "auto",
        mosaic=r.body.get("mosaic") or None,
    )
    s.set_cube(cube)
    return Json({"ok": True, "seconds": time.perf_counter() - t0})


@route("POST", "upload")
def upload(s: Session, r: Request) -> Json:
    name = Path(r.get("name")).name
    if r.stream is None or r.length <= 0 or r.length > MAX_UPLOAD:
        raise ApiError(400, "empty or too large upload")
    dest = s.upload_dir() / name
    remaining = r.length
    with open(dest, "wb") as f:
        while remaining > 0:
            chunk = r.stream.read(min(remaining, 1 << 22))
            if not chunk:
                break
            f.write(chunk)
            remaining -= len(chunk)
    if dest.suffix.lower() == ".hdr" and not any(
        dest.with_suffix(e).exists()
        for e in (".img", ".raw", ".dat", ".bsq", ".bil", ".bip", "")
        if dest.with_suffix(e) != dest
    ):
        return Json({"ok": True, "pending": True})  # ENVI header first; data file follows
    hdr = dest.with_suffix(".hdr")
    target = hdr if hdr.exists() else dest
    cube = load_cube(target, layout=r.get("layout", "auto"))
    cube.source = None
    s.set_cube(cube)
    return Json({"ok": True})


@route("POST", "transpose")
def transpose(s: Session, r: Request) -> Json:
    """Reinterpret the current cube's axes when the layout guess was wrong."""
    cube, _ = s.require()
    order = r.body.get("order")
    if sorted(order or []) != [0, 1, 2]:
        raise ApiError(400, "order must be a permutation of [0, 1, 2]")
    data = np.ascontiguousarray(np.transpose(cube.data, order))
    wl = cube.wavelengths if order[0] == 0 else None
    s.set_cube(Cube(data, wl, cube.name, cube.source, dict(cube.meta)))
    return Json({"ok": True})
