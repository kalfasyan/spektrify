"""Preprocessing steps, pipelines and their registry."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from spektrify.model import Cube
from spektrify.preprocess import Pipeline, make_step, param, register_step, step_schema


@pytest.fixture
def cube() -> Cube:
    data = np.arange(4 * 6 * 8, dtype=np.float32).reshape(4, 6, 8) - 10
    return Cube(data, np.array([400.0, 500, 600, 700]), name="t")


def test_parse_specs() -> None:
    p = Pipeline.parse(["clip", "bin:3", "crop:x0=1,x1=5", "bands:1,stop=3"])
    assert p.to_json() == [
        {"name": "clip", "params": {}},
        {"name": "bin", "params": {"factor": "3"}},
        {"name": "crop", "params": {"x0": "1", "x1": "5"}},
        {"name": "bands", "params": {"start": "1", "stop": "3"}},
    ]
    assert Pipeline.from_json(p.to_json()) == p


@pytest.mark.parametrize(
    "spec, match",
    [
        ("nope", "unknown step"),
        ("bin:x=1", "no parameter"),
        ("bin:abc", "factor"),
        ("clip:clip_negatives=maybe", "true/false"),
        ("crop:1,2", "first parameter"),
    ],
)
def test_parse_errors(spec: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Pipeline.parse([spec])


def test_apply_does_not_mutate_input(cube: Cube) -> None:
    before = cube.data.copy()
    out = Pipeline.parse(["clip:50", "bin:2"]).apply(cube)
    np.testing.assert_array_equal(cube.data, before)
    assert "preprocessing" not in cube.meta
    assert out.meta["preprocessing"].startswith("clip(percentile=50.0")
    assert Pipeline().apply(cube) is cube


def test_clip(cube: Cube) -> None:
    out = make_step("clip", {"percentile": 50})(cube)
    assert np.min(out.data) == 0  # negatives clipped
    for b in range(4):
        assert out.data[b].max() == pytest.approx(np.percentile(np.maximum(cube.data[b], 0), 50))


def test_crop_bands_bin(cube: Cube) -> None:
    assert make_step("crop", {"x0": 2, "y1": 3})(cube).data.shape == (4, 3, 6)
    b = make_step("bands", {"start": 1, "stop": 3})(cube)
    assert b.n_bands == 2 and b.wavelengths is not None
    np.testing.assert_array_equal(b.wavelengths, [500, 600])
    binned = make_step("bin", {"factor": 2})(cube)
    assert binned.data.shape == (4, 3, 4)
    assert binned.data[0, 0, 0] == pytest.approx(cube.data[0, :2, :2].mean())
    with pytest.raises(ValueError):
        make_step("crop", {"x0": 100})(cube)


def test_calibrate(cube: Cube, tmp_path) -> None:
    np.save(tmp_path / "white.npy", np.full(4, 110.0))
    out = make_step("calibrate", {"dark": "10", "white": str(tmp_path / "white.npy")})(cube)
    np.testing.assert_allclose(out.data, (cube.data - 10) / 100)
    np.save(tmp_path / "bad.npy", np.ones(3))
    with pytest.raises(ValueError, match="3 values"):
        make_step("calibrate", {"dark": str(tmp_path / "bad.npy")})(cube)


def test_custom_step_is_discoverable(cube: Cube) -> None:
    @register_step("scale", "Multiply by a constant.")
    @dataclass(frozen=True)
    class Scale:
        k: float = param(2.0, "Factor.")

        def __call__(self, c: Cube) -> Cube:
            return c.with_data(c.data * self.k)

    assert any(s["name"] == "scale" for s in step_schema())
    out = Pipeline.parse(["scale:3"]).apply(cube)
    np.testing.assert_allclose(out.data, cube.data * 3)
