"""Analysis backend: products, quality checks, band math, regions."""

from __future__ import annotations

import numpy as np
import pytest

from spektrify.compute import create_analyzer, register_backend
from spektrify.compute.bandmath import safe_eval
from spektrify.compute.regions import region_mask
from spektrify.io import demo_cube
from spektrify.model import Cube


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


def test_summary_maps_are_memoised_and_read_only(demo: Cube) -> None:
    an = create_analyzer(demo)
    mean = an.summary_map("mean")
    assert an.summary_map("mean") is mean and not mean.flags.writeable
    np.testing.assert_allclose(mean, np.nanmean(demo.data, axis=0), rtol=1e-6)
    np.testing.assert_allclose(an.band_math("mean - std"), mean - an.summary_map("std"))
    with pytest.raises(ValueError):
        an.summary_map("median")


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
