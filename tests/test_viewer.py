"""Tests for the spektrify backend (readers, analysis, routes, HTTP adapter)."""

from __future__ import annotations

import json
import urllib.request

import numpy as np
import pytest

from spektrify import show
from spektrify.compute import create_analyzer, register_backend
from spektrify.compute.bandmath import safe_eval
from spektrify.compute.regions import region_mask
from spektrify.io import demo_cube, load_cube, supported_suffixes
from spektrify.model import Cube
from spektrify.server.routes import ApiError, Binary, Json, Request, dispatch
from spektrify.server.session import Session


@pytest.fixture(scope="module")
def demo() -> Cube:
    return demo_cube(height=48, width=64, bands=32, seed=1)


@pytest.fixture(scope="module")
def session(demo: Cube) -> Session:
    return Session(demo)


def call(s: Session, name: str, method: str = "GET", body=None, **params):
    req = Request(params={k: [str(v)] for k, v in params.items()}, body=body or {})
    return dispatch(s, method, name, req)


# --------------------------------------------------------------------------- model & readers


def test_from_array_guesses_layout() -> None:
    hwc = np.random.rand(20, 30, 8).astype(np.float32)
    cube = Cube.from_array(hwc)
    assert (cube.n_bands, cube.height, cube.width) == (8, 20, 30)
    chw = np.random.rand(8, 20, 30)
    cube = Cube.from_array(chw, wavelengths=np.linspace(400, 900, 8))
    assert (cube.n_bands, cube.height, cube.width) == (8, 20, 30)
    assert cube.data.dtype == np.float32
    np.testing.assert_allclose(cube.data[3], chw[3], rtol=1e-6)


def test_from_array_explicit_layout_wins() -> None:
    a = np.random.rand(10, 10, 10)
    assert Cube.from_array(a, layout="chw").data[2, 3, 4] == pytest.approx(a[2, 3, 4])
    assert Cube.from_array(a, layout="hwc").data[2, 3, 4] == pytest.approx(a[3, 4, 2])


def test_readers_registered() -> None:
    for sfx in (".npy", ".npz", ".h5", ".hdf5", ".mat", ".tif", ".hdr"):
        assert sfx in supported_suffixes()


def test_npy_npz_roundtrip(tmp_path) -> None:
    a = np.random.rand(16, 12, 6).astype(np.float32)
    np.save(tmp_path / "c.npy", a)
    cube = load_cube(tmp_path / "c.npy")
    assert (cube.height, cube.width, cube.n_bands) == (16, 12, 6)
    wl = np.linspace(500, 700, 6)
    np.savez(tmp_path / "c.npz", cube=a, wavelengths=wl)
    cube = load_cube(tmp_path / "c.npz")
    np.testing.assert_allclose(cube.axis, wl)


def test_hdf5_reader(tmp_path) -> None:
    h5py = pytest.importorskip("h5py")
    a = np.random.rand(5, 14, 18).astype(np.float32)
    with h5py.File(tmp_path / "c.h5", "w") as f:
        f["data/cube"] = a
        f["wavelengths"] = np.linspace(400, 1000, 5)
    cube = load_cube(tmp_path / "c.h5", layout="chw")
    assert (cube.n_bands, cube.height, cube.width) == (5, 14, 18)
    np.testing.assert_allclose(cube.data, a)


def test_envi_reader(tmp_path) -> None:
    a = (np.random.rand(7, 9, 4) * 1000).astype("<u2")  # BIP = (lines, samples, bands)
    a.tofile(tmp_path / "scene.img")
    (tmp_path / "scene.hdr").write_text(
        "ENVI\nsamples = 9\nlines = 7\nbands = 4\nheader offset = 0\ndata type = 12\n"
        "interleave = bip\nbyte order = 0\nwavelength = {450, 550, 650, 750}\n"
    )
    cube = load_cube(tmp_path / "scene.img")  # opening the data file finds its header
    assert (cube.n_bands, cube.height, cube.width) == (4, 7, 9)
    np.testing.assert_allclose(cube.data[2], a[:, :, 2])
    np.testing.assert_allclose(cube.axis, [450, 550, 650, 750])


def test_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_cube("/nonexistent/cube.npy")


# --------------------------------------------------------------------------- analysis


def test_region_masks() -> None:
    rect = region_mask({"kind": "rect", "x0": 2, "y0": 3, "x1": 6, "y1": 5}, 10, 10)
    assert rect.sum() == 8 and rect[3, 2] and not rect[5, 2]
    ell = region_mask({"kind": "ellipse", "x0": 0, "y0": 0, "x1": 10, "y1": 10}, 10, 10)
    assert 60 < ell.sum() < 90 and ell[5, 5] and not ell[0, 0]
    tri = region_mask({"kind": "poly", "points": [[0, 0], [10, 0], [0, 10]]}, 10, 10)
    assert 40 < tri.sum() < 60 and tri[1, 1] and not tri[9, 9]
    assert region_mask({"kind": "rect", "x0": 50, "y0": 50, "x1": 60, "y1": 60}, 10, 10).sum() == 0


def test_bandmath_is_safe() -> None:
    env = {"a": np.ones(3), "sqrt": np.sqrt}
    np.testing.assert_allclose(safe_eval("sqrt(a * 4) + 1", env), [3, 3, 3])
    for bad in ("__import__('os')", "a.__class__", "open('x')", "[x for x in a]", "lambda: 1"):
        with pytest.raises((ValueError, NameError, SyntaxError)):
            safe_eval(bad, env)


def test_band_math_expressions(demo: Cube) -> None:
    an = create_analyzer(demo)
    ndvi = an.band_math("(b[20] - b[10]) / (b[20] + b[10])")
    assert ndvi.shape == (demo.height, demo.width)
    np.testing.assert_allclose(an.band_math("b[3]"), demo.data[3])
    assert an.band_math(f"nm({demo.axis[5]})").shape == ndvi.shape
    with pytest.raises(IndexError):
        an.band_math("b[999]")


def test_products_shapes(demo: Cube) -> None:
    an = create_analyzer(demo)
    hw = (demo.height, demo.width)
    assert an.project(3).shape == (3, *hw)
    assert an.rx().shape == hw
    assert an.pca_residual(3).shape == hw
    assert an.spectral_angle().shape == hw
    assert an.spectral_gradient().shape == hw
    for kind in ("mean", "std", "max", "argmax", "invalid"):
        assert an.summary_map(kind).shape == hw
    ex = an.pca(5)["explained"]
    assert len(ex) == 5 and all(ex[i] >= ex[i + 1] for i in range(4))


def test_spectral_angle_zero_at_reference(demo: Cube) -> None:
    an = create_analyzer(demo)
    ref = np.nan_to_num(demo.data[:, 10, 10])
    sam = an.spectral_angle(ref)
    assert sam[10, 10] == pytest.approx(0, abs=1e-3)


def test_quality_finds_planted_artifacts() -> None:
    cube = demo_cube()
    q = create_analyzer(cube).quality
    flagged = {f["band"]: " ".join(f["reasons"]) for f in q["flags"]}
    assert any("SNR" in r for r in flagged.values())
    assert any("NaN" in r for r in flagged.values())
    assert any("striping" in r for r in flagged.values())
    assert q["bad_columns"], "the planted dead column should be found"
    assert q["invalid_pixels"] > 0


def test_register_backend(demo: Cube) -> None:
    calls = []

    def factory(cube):
        calls.append(cube)
        return create_analyzer(cube, "numpy")

    register_backend("test-proxy", factory)
    create_analyzer(demo, "test-proxy")
    assert calls == [demo]
    with pytest.raises(ValueError):
        create_analyzer(demo, "nope")


# --------------------------------------------------------------------------- routes


def test_meta_route(session: Session, demo: Cube) -> None:
    r = call(session, "meta")
    assert isinstance(r, Json)
    m = r.obj
    assert (m["bands"], m["height"], m["width"]) == (demo.n_bands, demo.height, demo.width)
    json.dumps(m, allow_nan=False)  # the UI needs strict JSON


def test_band_and_spectrum_routes(session: Session, demo: Cube) -> None:
    r = call(session, "band", i=4)
    assert isinstance(r, Binary) and r.array.shape[-2:] == (demo.height, demo.width)
    sp = call(session, "spectrum", x=3, y=2).obj
    assert len(sp["values"]) == demo.n_bands
    with pytest.raises(ApiError) as e:
        call(session, "spectrum", x=-1, y=0)
    assert e.value.status == 400


def test_region_line_slice_routes(session: Session, demo: Cube) -> None:
    body = {"kind": "rect", "x0": 0, "y0": 0, "x1": 8, "y1": 8}
    st = call(session, "region", "POST", body).obj
    assert st["n"] == 64 and len(st["mean"]) == demo.n_bands
    ln = call(session, "line", x0=0, y0=0, x1=10, y1=10)
    assert ln.array.shape[1] == demo.n_bands
    sl = call(session, "slice", axis="col", i=5)
    assert sl.array.shape == (demo.n_bands, demo.height)


def test_product_routes(session: Session) -> None:
    for kind in ("pca", "rx", "residual", "sam", "gradient", "mean"):
        r = call(session, "product", kind=kind)
        assert r.array.ndim == 3, kind
    r = call(session, "product", "POST", {"expr": "b[1] * 2"}, kind="math")
    assert r.meta["expr"] == "b[1] * 2"
    with pytest.raises(ApiError):
        call(session, "product", kind="nope")


def test_unknown_route_and_no_cube() -> None:
    with pytest.raises(ApiError) as e:
        call(Session(demo_cube(16, 16, 8)), "does-not-exist")
    assert e.value.status == 404
    with pytest.raises(LookupError):  # the HTTP adapter maps this to 404
        call(Session(), "band", i=0)


def test_quality_and_3d_routes(session: Session, demo: Cube) -> None:
    assert "flags" in call(session, "quality").obj
    c = call(session, "correlation").array
    assert c.size == demo.n_bands**2
    assert call(session, "stripes", which="columns").array.shape[0] == demo.n_bands
    assert call(session, "volume", max=32).array.ndim == 3
    sc = call(session, "scatter", n=500)
    assert sc.meta["n"] <= 500


# --------------------------------------------------------------------------- HTTP adapter


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
