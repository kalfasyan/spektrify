"""API routes (transport-free) and the HTTP adapter."""

from __future__ import annotations

import json
import urllib.request

import numpy as np
import pytest

from spektrify import show
from spektrify.io import demo_cube
from spektrify.model import Cube
from spektrify.server.routes import ApiError, Binary, Json
from spektrify.server.session import Session


def test_meta_route(call, session: Session, demo: Cube) -> None:
    r = call(session, "meta")
    assert isinstance(r, Json)
    m = r.obj
    assert (m["bands"], m["height"], m["width"]) == (demo.n_bands, demo.height, demo.width)
    json.dumps(m, allow_nan=False)  # the UI needs strict JSON


def test_band_and_spectrum_routes(call, session: Session, demo: Cube) -> None:
    r = call(session, "band", i=4)
    assert isinstance(r, Binary) and r.array.shape[-2:] == (demo.height, demo.width)
    sp = call(session, "spectrum", x=3, y=2).obj
    assert len(sp["values"]) == demo.n_bands
    with pytest.raises(ApiError) as e:
        call(session, "spectrum", x=-1, y=0)
    assert e.value.status == 400


def test_region_line_slice_routes(call, session: Session, demo: Cube) -> None:
    body = {"kind": "rect", "x0": 0, "y0": 0, "x1": 8, "y1": 8}
    st = call(session, "region", "POST", body).obj
    assert st["n"] == 64 and len(st["mean"]) == demo.n_bands
    ln = call(session, "line", x0=0, y0=0, x1=10, y1=10)
    assert ln.array.shape[1] == demo.n_bands
    sl = call(session, "slice", axis="col", i=5)
    assert sl.array.shape == (demo.n_bands, demo.height)


def test_product_routes(call, session: Session) -> None:
    for kind in ("pca", "rx", "residual", "sam", "gradient", "mean"):
        r = call(session, "product", kind=kind)
        assert r.array.ndim == 3, kind
    r = call(session, "product", "POST", {"expr": "b[1] * 2"}, kind="math")
    assert r.meta["expr"] == "b[1] * 2"
    with pytest.raises(ApiError):
        call(session, "product", kind="nope")


def test_unknown_route_and_no_cube(call) -> None:
    with pytest.raises(ApiError) as e:
        call(Session(demo_cube(16, 16, 8)), "does-not-exist")
    assert e.value.status == 404
    with pytest.raises(LookupError):  # the HTTP adapter maps this to 404
        call(Session(), "band", i=0)


def test_quality_and_3d_routes(call, session: Session, demo: Cube) -> None:
    assert "flags" in call(session, "quality").obj
    c = call(session, "correlation").array
    assert c.size == demo.n_bands**2
    assert call(session, "stripes", which="columns").array.shape[0] == demo.n_bands
    assert call(session, "volume", max=32).array.ndim == 3
    sc = call(session, "scatter", n=500)
    assert sc.meta["n"] <= 500


def test_http_server_serves_ui_and_api() -> None:
    v = show(np.random.rand(12, 10, 5).astype(np.float32), port=0, open_browser=False)
    try:
        html = urllib.request.urlopen(v.url, timeout=5).read().decode()
        assert 'id="root"' in html
        meta = json.load(urllib.request.urlopen(v.url + "api/meta", timeout=5))
        assert meta["bands"] == 5
        with urllib.request.urlopen(v.url + "api/band?i=2", timeout=5) as resp:
            info = json.loads(resp.headers["X-Meta"])
            arr = np.frombuffer(resp.read(), "<f4").reshape(info["shape"])
        assert arr.shape[-2:] == (12, 10)
    finally:
        v.stop()


def test_preprocessing_routes(call, session: Session, demo: Cube) -> None:
    schema = call(session, "steps").obj
    assert {s["name"] for s in schema["steps"]} >= {"clip", "bin", "crop", "calibrate"}
    gen = session.generation
    r = call(session, "pipeline", "POST", {"steps": [{"name": "bin", "params": {"factor": 2}}]})
    assert r.obj["steps"][0]["name"] == "bin"
    meta = call(session, "meta").obj
    assert (meta["height"], meta["width"]) == (demo.height // 2, demo.width // 2)
    assert meta["pipeline"] == r.obj["steps"] and session.generation == gen + 1
    call(session, "pipeline", "POST", {"steps": []})  # back to raw
    assert call(session, "meta").obj["height"] == demo.height
    with pytest.raises(ApiError) as e:
        call(session, "pipeline", "POST", {"steps": [{"name": "nope"}]})
    assert e.value.status == 400
