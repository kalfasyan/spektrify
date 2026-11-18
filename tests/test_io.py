"""Model and file readers."""

from __future__ import annotations

import numpy as np
import pytest

from spektrify.io import demosaic, demosaic_methods, load_cube, supported_suffixes
from spektrify.model import Cube


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


# --------------------------------------------------------------------------- demosaicing


def _mosaic(cube_hwc: np.ndarray, t: int) -> np.ndarray:
    """Inverse of block demosaicing: interleave t² channels into a 2-D sensor frame."""
    h, w, _ = cube_hwc.shape
    return cube_hwc.reshape(h, w, t, t).transpose(0, 2, 1, 3).reshape(h * t, w * t)


def test_block_demosaic_inverts_mosaicing() -> None:
    cube = np.random.rand(6, 5, 16).astype(np.float32)
    np.testing.assert_array_equal(demosaic(_mosaic(cube, 4), 4, "block"), cube)


def test_bilinear_demosaic_full_resolution_and_exact_on_samples() -> None:
    cube = np.random.rand(6, 5, 9).astype(np.float32)
    raw = _mosaic(cube, 3)
    out = demosaic(raw, 3, "bilinear")
    assert out.shape == (18, 15, 9)
    # Channel k = dy·3 + dx is exact where the sensor sampled it.
    np.testing.assert_allclose(out[1::3, 2::3, 1 * 3 + 2], cube[..., 5], rtol=1e-6)
    # A constant scene stays constant.
    flat = demosaic(np.full((12, 12), 7.0), 4, "bilinear")
    np.testing.assert_allclose(flat, 7.0)


def test_demosaic_errors() -> None:
    with pytest.raises(ValueError, match="unknown demosaic"):
        demosaic(np.zeros((8, 8)), 2, "nope")
    with pytest.raises(ValueError, match="2-D"):
        demosaic(np.zeros((8, 8, 3)), 2)
    assert {"block", "bilinear"} <= set(demosaic_methods())


def test_spektro_raw_mosaic_file(tmp_path) -> None:
    """spektro's HDF5 layout: ``mosaic_image`` (H, W) + ``central_wavelengths`` (t²)."""
    h5py = pytest.importorskip("h5py")
    cube = np.random.rand(10, 12, 25).astype(np.float32)
    wl = np.linspace(600, 900, 25)
    with h5py.File(tmp_path / "raw.h5", "w") as f:
        f["mosaic_image"] = _mosaic(cube, 5)
        f["central_wavelengths"] = wl
    loaded = load_cube(tmp_path / "raw.h5")  # tile size 5 inferred from 25 filters
    assert (loaded.height, loaded.width, loaded.n_bands) == (10, 12, 25)
    np.testing.assert_allclose(loaded.data, cube.transpose(2, 0, 1))
    np.testing.assert_allclose(loaded.axis, wl)
    full = load_cube(tmp_path / "raw.h5", demosaic_method="bilinear")
    assert (full.height, full.width) == (50, 60)
    assert "bilinear" in full.meta["demosaiced"]


def test_forced_mosaic_on_npy(tmp_path) -> None:
    np.save(tmp_path / "raw.npy", _mosaic(np.random.rand(4, 4, 4), 2))
    assert load_cube(tmp_path / "raw.npy", mosaic=2).n_bands == 4
