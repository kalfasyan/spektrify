"""The correction and spectral preprocessing steps, each against a planted, known defect."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from spektrify.model import Cube
from spektrify.preprocess import Pipeline, make_step, references, step_schema
from spektrify.preprocess import _ops as ops
from spektrify.preprocess.corrections import Align
from spektrify.preprocess.steps import Calibrate


def scene(h: int = 96, w: int = 128, n: int = 6, seed: int = 0) -> np.ndarray:
    """Smooth random image with edges, the same in every band up to a per-band gain."""
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w), np.float32)
    for _ in range(25):
        y, x = rng.integers(0, h - 20), rng.integers(0, w - 20)
        img[y : y + rng.integers(8, 20), x : x + rng.integers(8, 20)] += rng.uniform(0.2, 1)
    gains = np.linspace(0.6, 1.4, n, dtype=np.float32)
    return gains[:, None, None] * (img + 0.2)[None]


@pytest.fixture
def cube() -> Cube:
    return Cube(scene(), np.linspace(450, 700, 6), name="scene")


def test_every_new_step_is_registered_and_round_trips() -> None:
    names = {s["name"] for s in step_schema()}
    new = {"badpixels", "flatfield", "whitebalance", "destripe", "align", "smooth", "snv", "msc"}
    assert new | {"absorbance"} <= names
    for n in sorted(new | {"absorbance"}):
        assert Pipeline.parse([n]).apply(Cube(scene(n=10))).data.shape == (10, 96, 128)


def test_schema_marks_path_parameters() -> None:
    params = {s["name"]: {p["name"]: p["kind"] for p in s["params"]} for s in step_schema()}
    assert params["calibrate"]["dark"] == "path" and params["calibrate"]["clamp"] == "bool"
    assert params["flatfield"]["frame"] == "path" and params["flatfield"]["degree"] == "int"
    assert params["align"]["shifts"] == "path"


# ----------------------------------------------------------------------------- references


def test_reference_formats(cube: Cube, tmp_path: Path) -> None:
    np.savetxt(tmp_path / "s.csv", np.arange(6.0), delimiter=",")
    np.save(tmp_path / "f.npy", np.ones((cube.height, cube.width)))
    assert references.spectrum(str(tmp_path / "s.csv"), cube).tolist() == list(range(6))
    assert references.image(str(tmp_path / "f.npy"), cube).shape == (1, 96, 128)
    assert references.per_band(np.arange(6.0), cube).shape == (6, 1, 1)  # array passed in Python
    with pytest.raises(FileNotFoundError):
        references.load_array(str(tmp_path / "missing.npy"))
    np.save(tmp_path / "small.npy", np.ones((5, 5)))
    with pytest.raises(ValueError, match="5 × 5"):
        references.image(str(tmp_path / "small.npy"), cube)


def test_calibrate_clamp_eps_and_arrays(cube: Cube) -> None:
    dark = np.full(6, 0.5, np.float32)
    white = np.full(6, 0.5, np.float32)  # white == dark: undefined
    out = Calibrate(dark=dark, white=white)(cube)
    assert np.isnan(out.data).all()
    out = Calibrate(dark="1.0", clamp=True)(cube)
    assert np.min(out.data) >= 0 and (out.data == 0).any()
    out = make_step("calibrate", {"dark": "0.1", "white": "1.1"})(cube)
    np.testing.assert_allclose(out.data, cube.data - 0.1)


# ----------------------------------------------------------------------------- badpixels


def test_badpixels_repairs_hot_dead_nan_and_lines(cube: Cube) -> None:
    clean = cube.data.copy()
    d = clean.copy()
    d[2, 40, 50] = 50.0  # hot
    d[3, 10, 10] = 0.0  # dead
    d[1, 60, 70] = np.nan
    d[:, :, 90] = 0.0  # dead column in every band
    d[4, 30, :] += 5.0  # bad row in one band
    out = make_step("badpixels", {})(cube.with_data(d))
    assert np.isfinite(out.data).all()
    err = np.abs(out.data - clean)
    assert err[2, 40, 50] < 0.5 and err[3, 10, 10] < 0.5 and err[1, 60, 70] < 0.5
    assert np.median(err[:, :, 90]) < 0.02  # (interpolation can't recover an edge in the line)
    assert np.median(err[4, 30, :]) < 0.02
    # Untouched pixels stay exactly as they were.
    keep = np.ones(clean.shape, bool)
    keep[:, :, 88:93] = False
    keep[4, 28:33, :] = False
    keep[2, 38:43, 48:53] = False
    keep[3, 8:13, 8:13] = False
    keep[1, 58:63, 68:73] = False
    assert (err[keep] == 0).mean() > 0.97  # thin real structure may be mistaken for a line


def test_badpixels_leaves_a_clean_cube_alone(cube: Cube) -> None:
    out = make_step("badpixels", {"lines": False})(cube)
    assert (out.data != cube.data).mean() < 0.001


def test_badpixels_rejects_bad_size(cube: Cube) -> None:
    with pytest.raises(ValueError, match="3 or 5"):
        make_step("badpixels", {"size": 4})(cube)


# ----------------------------------------------------------------------------- flatfield


def vignette(h: int, w: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((yy - h / 2) / h) ** 2 + ((xx - w / 2) / w) ** 2
    return (1.0 - 1.6 * r2).astype(np.float32)


def test_flatfield_from_frame(cube: Cube, tmp_path: Path) -> None:
    v = vignette(cube.height, cube.width)
    np.save(tmp_path / "flat.npy", 100 * v)
    out = make_step("flatfield", {"frame": str(tmp_path / "flat.npy")})(
        cube.with_data(cube.data * v)
    )
    ratio = out.data / cube.data
    # equal up to a global scale (the gain is normalised to unit median)
    assert ratio.std() / ratio.mean() < 1e-3


def test_flatfield_estimated_reduces_illumination_gradient() -> None:
    flat = np.ones((4, 96, 128), np.float32)
    v = vignette(96, 128)
    out = make_step("flatfield", {"degree": 2})(Cube(flat * v))
    assert out.data.std() < 0.05 * (flat * v).std()


def test_flatfield_frame_size_mismatch(cube: Cube, tmp_path: Path) -> None:
    np.save(tmp_path / "f.npy", np.ones((10, 10)))
    with pytest.raises(ValueError, match="10 × 10"):
        make_step("flatfield", {"frame": str(tmp_path / "f.npy")})(cube)


# ----------------------------------------------------------------------------- whitebalance


def test_whitebalance_patch_reference_and_gray_world(cube: Cube, tmp_path: Path) -> None:
    out = make_step("whitebalance", {"x0": 0, "y0": 0, "x1": 8, "y1": 8})(cube)
    np.testing.assert_allclose(out.data[:, :8, :8].mean(axis=(1, 2)), 1.0, rtol=1e-4)
    spec = cube.data.mean(axis=(1, 2))
    np.save(tmp_path / "w.npy", spec)
    out = make_step("whitebalance", {"method": "reference", "reference": str(tmp_path / "w.npy")})(
        cube
    )
    np.testing.assert_allclose(out.data.mean(axis=(1, 2)), 1.0, rtol=1e-4)
    out = make_step("whitebalance", {"method": "gray-world"})(cube)
    means = out.data.mean(axis=(1, 2))
    np.testing.assert_allclose(means, means[0], rtol=1e-4)
    with pytest.raises(ValueError, match="needs a reference"):
        make_step("whitebalance", {"method": "reference"})(cube)
    with pytest.raises(ValueError, match="method must be"):
        make_step("whitebalance", {"method": "nope"})(cube)


# ----------------------------------------------------------------------------- destripe


@pytest.mark.parametrize("mode", ["offset", "gain"])
def test_destripe_columns(mode: str) -> None:
    rng = np.random.default_rng(1)
    base = np.full((3, 80, 120), 1.0, np.float32) + 0.01 * rng.standard_normal((3, 80, 120)).astype(
        np.float32
    )
    stripe = 1 + 0.2 * rng.standard_normal(120).astype(np.float32)
    striped = base * stripe if mode == "gain" else base + (stripe - 1)
    out = make_step("destripe", {"mode": mode})(Cube(striped))
    col = lambda a: a.mean(axis=1).std()  # noqa: E731
    assert col(out.data) < 0.2 * col(striped)


def test_destripe_rows_and_errors() -> None:
    rng = np.random.default_rng(4)
    d = (
        np.ones((2, 80, 80), np.float32)
        + (0.2 * rng.standard_normal(80)).astype(np.float32)[None, :, None]
    )
    out = make_step("destripe", {"axis": "rows"})(Cube(d))
    assert out.data.mean(axis=2).std() < 0.2 * d.mean(axis=2).std()
    with pytest.raises(ValueError, match="axis"):
        make_step("destripe", {"axis": "x"})(Cube(d))


# ----------------------------------------------------------------------------- smooth / snv / msc


def test_savgol_matches_polynomial_and_derivative() -> None:
    n = 40
    x = np.linspace(0, 2, n)
    y = 3 + 2 * x - x**2  # an order-2 polynomial is reproduced exactly, edges included
    cube = Cube(
        np.broadcast_to(y[:, None, None], (n, 4, 4)).astype(np.float32),
        500.0 + 10 * np.arange(n, dtype=float),
    )
    smooth = make_step("smooth", {"window": 7, "order": 2})(cube)
    np.testing.assert_allclose(smooth.data[:, 0, 0], y, atol=1e-4)
    d1 = make_step("smooth", {"window": 7, "order": 2, "deriv": 1})(cube)
    dx = x[1] - x[0]  # one band is 10 nm and dx in x
    np.testing.assert_allclose(d1.data[:, 0, 0], (2 - 2 * x) * dx / 10, atol=1e-5)


def test_smooth_reduces_noise_and_validates() -> None:
    rng = np.random.default_rng(2)
    clean = np.sin(np.linspace(0, 3, 60))[:, None, None] * np.ones((1, 5, 5))
    noisy = Cube((clean + 0.1 * rng.standard_normal(clean.shape)).astype(np.float32))
    out = make_step("smooth", {"window": 15, "order": 2})(noisy)
    assert np.abs(out.data - clean).mean() < 0.5 * np.abs(noisy.data - clean).mean()
    for bad in ({"window": 4}, {"order": 7}, {"deriv": 3}, {"window": 99}):
        with pytest.raises(ValueError):
            make_step("smooth", bad)(noisy)


def test_snv_gives_zero_mean_unit_std(cube: Cube) -> None:
    out = make_step("snv", {})(cube).data
    np.testing.assert_allclose(out.mean(axis=0), 0, atol=1e-5)
    np.testing.assert_allclose(out.std(axis=0), 1, atol=1e-4)
    flat = Cube(np.ones((4, 3, 3), np.float32))
    assert np.isnan(make_step("snv", {})(flat).data).all()


def test_msc_removes_multiplicative_and_additive_scatter(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    ref = (1 + np.sin(np.linspace(0, 6, 50))).astype(np.float32)
    a = rng.uniform(-0.2, 0.2, (8, 8)).astype(np.float32)
    b = rng.uniform(0.7, 1.4, (8, 8)).astype(np.float32)
    data = a[None] + b[None] * ref[:, None, None]
    np.save(tmp_path / "ref.npy", ref)
    out = make_step("msc", {"reference": str(tmp_path / "ref.npy")})(Cube(data))
    np.testing.assert_allclose(out.data, np.broadcast_to(ref[:, None, None], data.shape), atol=1e-4)
    out = make_step("msc", {})(Cube(data))  # mean-spectrum reference
    assert np.max(out.data.std(axis=(1, 2))) < np.max(data.std(axis=(1, 2)))
    with pytest.raises(ValueError, match="flat"):
        make_step("msc", {})(Cube(np.ones((5, 3, 3), np.float32)))


def test_absorbance(cube: Cube) -> None:
    c = cube.with_data(np.full((3, 4, 4), 0.1, np.float32))
    np.testing.assert_allclose(make_step("absorbance", {})(c).data, 1.0, atol=1e-6)
    zero = cube.with_data(np.zeros((3, 4, 4), np.float32))
    assert np.isfinite(make_step("absorbance", {})(zero).data).all()


# ----------------------------------------------------------------------------- align


def shifted_cube(shifts: list[tuple[float, float]], seed: int = 0) -> tuple[Cube, np.ndarray]:
    base = scene(96, 128, 1, seed)[0]
    # make the content differ per band: a spectral gain and a bit of noise
    rng = np.random.default_rng(seed + 10)
    bands = []
    for i, (dx, dy) in enumerate(shifts):
        sh = ops.shift_image(base, dx, dy)
        bands.append(
            np.nan_to_num(sh, nan=0.0) * (0.6 + 0.1 * i) + 0.01 * rng.standard_normal(base.shape)
        )
    return Cube(np.stack(bands).astype(np.float32)), np.array(shifts)


def test_align_recovers_planted_shifts() -> None:
    planted = [(0, 0), (3.4, -2.1), (-4.0, 1.5), (1.25, 2.75), (0, 0)]
    planted[2] = (planted[2][0], planted[2][1])
    cube, truth = shifted_cube(planted)
    ref = 0
    out = Align(reference=ref, max_shift=6)(cube)
    est = np.array(out.meta["align_shifts"])
    assert np.abs(est - truth).max() < 0.25
    # after correction the interior matches the reference band
    inner = (slice(10, -10), slice(10, -10))
    for b in range(1, 4):
        a = out.data[b][inner] / (0.6 + 0.1 * b)
        r = cube.data[0][inner] / 0.6
        assert np.corrcoef(a.ravel(), r.ravel())[0, 1] > 0.98


def test_align_ignores_unrelated_noise_bands() -> None:
    cube, _ = shifted_cube([(0, 0), (0, 0)])
    rng = np.random.default_rng(5)
    noisy = np.concatenate([cube.data, rng.standard_normal((1, 96, 128)).astype(np.float32)])
    out = Align(reference=0, max_shift=5, min_confidence=0.1)(cube.with_data(noisy))
    assert out.meta["align_shifts"][2] == [0.0, 0.0]
    np.testing.assert_array_equal(out.data[2], noisy[2])


def test_align_uses_given_shifts_and_marks_edges(tmp_path: Path) -> None:
    c = Cube(np.ones((2, 20, 20), np.float32))
    np.savetxt(tmp_path / "s.csv", [[0, 0], [2, 0]], delimiter=",")
    out = make_step("align", {"shifts": str(tmp_path / "s.csv")})(c)
    # dx=2 means the band is displaced by +2 px: correcting moves it back, leaving NaN on the right
    assert np.isnan(out.data[1, :, -2:]).all() and np.isfinite(out.data[1, :, :-2]).all()
    with pytest.raises(ValueError, match="rows"):
        np.savetxt(tmp_path / "bad.csv", [[0, 0]], delimiter=",")
        make_step("align", {"shifts": str(tmp_path / "bad.csv")})(c)


def test_align_errors(cube: Cube) -> None:
    with pytest.raises(ValueError, match="outside"):
        make_step("align", {"reference": 9})(cube)
    with pytest.raises(ValueError, match="too small"):
        make_step("align", {})(Cube(np.ones((3, 8, 8), np.float32)))


def test_pipeline_records_array_parameters_compactly(cube: Cube) -> None:
    out = Calibrate(dark=np.zeros(6, np.float32))(cube)
    assert out.data.shape == cube.data.shape
    from spektrify.preprocess.base import describe

    assert "<array 6>" in describe(Calibrate(dark=np.zeros(6)))
