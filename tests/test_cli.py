"""The ``spektrify`` command line."""

from __future__ import annotations

import json

import numpy as np
import pytest
from typer.testing import CliRunner

from spektrify.cli import app
from spektrify.io import demo_cube

runner = CliRunner()


@pytest.fixture(scope="module")
def cube_file(tmp_path_factory) -> str:
    c = demo_cube(64, 80, 24)
    path = tmp_path_factory.mktemp("cli") / "demo.npz"
    np.savez(path, cube=c.data.transpose(1, 2, 0), wavelengths=c.wavelengths)
    return str(path)


def test_version_and_help() -> None:
    assert runner.invoke(app, ["--version"]).output.startswith("spektrify ")
    out = runner.invoke(app, ["--help"]).output
    for cmd in ("view", "info", "quality", "convert", "demo", "steps"):
        assert cmd in out


def test_info_json_with_steps(cube_file: str) -> None:
    r = runner.invoke(app, ["info", cube_file, "--json", "-s", "bin:2"])
    assert r.exit_code == 0, r.output
    info = json.loads(r.output)
    assert (info["height"], info["width"], info["bands"]) == (32, 40, 24)
    assert "bin(factor=2)" in info["meta"]["preprocessing"]


def test_quality_strict_exit_code(cube_file: str) -> None:
    r = runner.invoke(app, ["quality", cube_file, "--json"])
    assert r.exit_code == 0 and json.loads(r.output)["flags"]
    assert runner.invoke(app, ["quality", cube_file, "--strict"]).exit_code == 1


def test_convert_roundtrip(cube_file: str, tmp_path) -> None:
    out = tmp_path / "small.npz"
    r = runner.invoke(app, ["convert", cube_file, str(out), "-s", "bands:0,stop=10"])
    assert r.exit_code == 0, r.output
    with np.load(out) as z:
        assert z["cube"].shape == (64, 80, 10) and z["wavelengths"].shape == (10,)


def test_bad_input_is_a_clean_error(cube_file: str) -> None:
    r = runner.invoke(app, ["info", cube_file, "-s", "nope"])
    assert r.exit_code == 2 and "unknown step" in r.output
    assert runner.invoke(app, ["info", "/no/such/file.npy"]).exit_code == 2


def test_steps_listing() -> None:
    names = {s["name"] for s in json.loads(runner.invoke(app, ["steps", "--json"]).output)}
    assert {"clip", "calibrate", "crop", "bands", "bin"} <= names


def test_demo_files(tmp_path) -> None:
    pytest.importorskip("h5py")
    cube_h5, raw_h5 = tmp_path / "demo.h5", tmp_path / "raw.h5"
    assert (
        runner.invoke(app, ["demo", str(cube_h5), "--size", "40x50", "--bands", "12"]).exit_code
        == 0
    )
    info = json.loads(runner.invoke(app, ["info", str(cube_h5), "--json"]).output)
    assert (info["height"], info["width"], info["bands"]) == (40, 50, 12)
    r = runner.invoke(app, ["demo", str(raw_h5), "--raw", "--size", "40x50"])
    assert r.exit_code == 0, r.output
    info = json.loads(runner.invoke(app, ["info", str(raw_h5), "--json"]).output)
    assert (info["height"], info["width"], info["bands"]) == (40, 50, 16)  # demosaiced on open
    assert runner.invoke(app, ["demo", str(tmp_path / "x.h5"), "--size", "big"]).exit_code == 2
