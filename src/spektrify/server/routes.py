"""The viewer's HTTP API as plain functions, independent of any web framework.

Each route takes ``(session, request)`` and returns a :class:`Json` or :class:`Binary`
response. :mod:`spektrify.server.http` adapts them to the stdlib server; another
transport (FastAPI, aiohttp, a Tauri/Rust shell, tests) can call :func:`dispatch` directly.
The wire contract is documented in ``docs/architecture.md``.
"""

from __future__ import annotations

import io
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from spektrify.compute import region_mask
from spektrify.compute._util import finite_list
from spektrify.io import DEMOS, demosaic_methods, load_cube, supported_suffixes
from spektrify.learn import Lesson, check_answer, labels_of, lesson_json, summary_json
from spektrify.model import Cube
from spektrify.preprocess import Pipeline, step_schema
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
    stream: io.BufferedIOBase | None = None  # raw body, for uploads
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
            "band_stats": an.band_stats,  # non-finite values are nulled by the JSON encoder
            "mean_spectrum": finite_list(an.mean_spectrum),
            "invalid_pixels": int((~an.finite_mask).sum()),
            "pipeline": s.pipeline.to_json(),
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
    suffixes = set(supported_suffixes())
    if r.get("refs", ""):  # picking a calibration file: spectra and shift tables are text too
        suffixes |= {".csv", ".txt"}
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
        demosaic_method=r.body.get("demosaic") or "block",
    )
    s.set_cube(cube, _pipeline(r.body.get("steps") or []))
    return Json({"ok": True, "seconds": time.perf_counter() - t0})


@route("POST", "demo")
def demo(s: Session, r: Request) -> Json:
    """Show a built-in synthetic cube by name (``scene`` or ``capture``)."""
    name = r.body.get("name") or "scene"
    if name not in DEMOS:
        raise ApiError(400, f"unknown demo {name!r}; choose from {', '.join(DEMOS)}")
    s.set_cube(DEMOS[name]())
    return Json({"ok": True})


# --------------------------------------------------------------------------- preprocessing


def _pipeline(items: Any) -> Pipeline:
    try:
        return Pipeline.from_json(items)
    except (KeyError, TypeError, ValueError) as e:
        raise ApiError(400, str(e)) from e


@route("GET", "steps")
def steps(s: Session, r: Request) -> Json:
    """The preprocessing steps the viewer can offer, with their parameters."""
    return Json({"steps": step_schema(), "demosaic": demosaic_methods()})


@route("POST", "pipeline")
def pipeline(s: Session, r: Request) -> Json:
    """Replace the preprocessing pipeline; the raw cube is re-processed and re-displayed."""
    p = _pipeline(r.body.get("steps") or [])
    t0 = time.perf_counter()
    s.set_pipeline(p)
    return Json({"ok": True, "steps": p.to_json(), "seconds": time.perf_counter() - t0})


@route("POST", "upload")
def upload(s: Session, r: Request) -> Json:
    name = Path(r.get("name")).name
    if r.stream is None or r.length <= 0 or r.length > MAX_UPLOAD:
        raise ApiError(400, "empty or too large upload")
    dest = s.upload_dir() / name
    remaining = r.length
    with dest.open("wb") as f:
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
    s.require()
    cube = s.raw
    assert cube is not None  # require() guarantees a loaded cube
    order = list(r.body.get("order") or [])
    if sorted(order) != [0, 1, 2]:
        raise ApiError(400, "order must be a permutation of [0, 1, 2]")
    data = np.ascontiguousarray(np.transpose(cube.data, order))
    wl = cube.wavelengths if order[0] == 0 else None
    s.set_cube(Cube(data, wl, cube.name, cube.source, dict(cube.meta)), s.pipeline)
    return Json({"ok": True})


# --------------------------------------------------------------------------- lessons


@route("GET", "lessons")
def lessons(s: Session, r: Request) -> Json:
    """The lesson catalog, plus which built-in demo (if any) is on display."""
    cube = s.cube
    return Json(
        {
            "lessons": [summary_json(le) for le in s.lessons().values()],
            "demo": None if cube is None else cube.meta.get("demo"),
            "labelled": cube is not None and labels_of(cube) is not None,
        }
    )


def _lesson(s: Session, lesson_id: str) -> Lesson:
    lesson = s.lessons().get(lesson_id)
    if lesson is None:
        raise ApiError(404, f"no lesson {lesson_id!r}")
    return lesson


@route("GET", "lesson")
def lesson(s: Session, r: Request) -> Json:
    """One lesson, resolved for the cube on display (band references → indices)."""
    return Json(lesson_json(_lesson(s, r.get("id")), s.cube))


@route("POST", "lesson-check")
def lesson_check(s: Session, r: Request) -> Json:
    """Grade an answer. Body ``{id, step, answer: {x, y} | {band} | {choice}}``."""
    le = _lesson(s, str(r.body.get("id")))
    i = r.body.get("step")
    if not isinstance(i, int) or not 0 <= i < len(le.steps) or le.steps[i].task is None:
        raise ApiError(400, "that step has no task")
    cube, _ = s.require()
    try:
        return Json(check_answer(le.steps[i].task, dict(r.body.get("answer") or {}), cube))
    except (KeyError, TypeError) as e:
        raise ApiError(400, f"bad answer: {e}") from e
