"""Image operations used by band math and the Learn lessons."""

from __future__ import annotations

import numpy as np
import pytest

from spektrify.compute import imageops as ops
from spektrify.compute.numpy_backend import NumpyAnalyzer
from spektrify.io import demo_cube


def _square(n: int = 32, lo: int = 10, hi: int = 20) -> np.ndarray:
    a = np.zeros((n, n), np.float32)
    a[lo:hi, lo:hi] = 1
    return a


def test_blurs_keep_constants_and_reduce_noise() -> None:
    flat = np.full((20, 30), 3.0, np.float32)
    for f in (ops.box, ops.gauss, ops.median, ops.lowpass):
        assert np.allclose(f(flat), 3.0, atol=1e-4), f.__name__
    noise = np.random.default_rng(0).normal(0, 1, (128, 128)).astype(np.float32)
    assert 4 < 1 / float(np.std(ops.box(noise, 2))) < 6  # 5x5 mean: std / 5
    assert float(np.std(ops.gauss(noise, 1.5))) < float(np.std(ops.median(noise, 1)))


def test_derivatives_have_the_documented_signs() -> None:
    ramp = np.tile(np.arange(16, dtype=np.float32), (8, 1))  # brighter to the right
    assert np.allclose(ops.dx(ramp)[:, 1:-1], 1.0)
    assert np.allclose(ops.dy(ramp), 0.0)
    assert np.allclose(ops.dy(ramp.T)[1:-1], 1.0)
    assert np.allclose(ops.grad(ramp)[:, 1:-1], 1.0)
    assert np.allclose(ops.laplace(ramp)[:, 1:-1], 0.0)


def test_median_removes_isolated_impulses_but_not_large_blobs() -> None:
    a = np.zeros((20, 20), np.float32)
    a[5, 5] = 100
    a[10:14, 10:14] = 100
    out = ops.median(a, 1)
    assert out[5, 5] == 0 and out[12, 12] == 100
    assert np.max(ops.median(a, 3)) == 0


def test_point_operations() -> None:
    a = np.linspace(0, 1, 100, dtype=np.float32).reshape(10, 10)
    assert len(np.unique(ops.quantize(a, 4))) == 4
    eq = ops.equalize(a**4)
    assert abs(float(np.mean(eq)) - 0.5) < 0.05  # a flat histogram
    st = ops.stretch(a)
    assert np.min(st) == 0 and np.max(st) == 1
    bimodal = np.r_[np.full(500, 0.2), np.full(500, 0.8)].reshape(20, 50).astype(np.float32)
    assert 0.2 < ops.otsu(bimodal) <= 0.8
    assert ops.subsample(a, 5).shape == a.shape


def test_highpass_is_what_lowpass_removes() -> None:
    a = np.random.default_rng(1).normal(size=(24, 40)).astype(np.float32)
    assert np.allclose(ops.lowpass(a, 0.2) + ops.highpass(a, 0.2), a, atol=1e-4)
    stripes = np.tile((np.arange(40) % 4 < 2).astype(np.float32), (24, 1))
    spec = ops.fft(stripes)
    row, _ = np.unravel_index(int(np.argmax(spec)), spec.shape)
    assert row == 12  # vertical stripes -> spikes on the horizontal axis through the centre


def test_morphology() -> None:
    sq = _square()
    assert ops.erode(sq, 1).sum() == 8 * 8
    assert ops.dilate(sq, 1).sum() == 12 * 12
    gap = sq.copy()
    gap[:, 15] = 0
    assert np.array_equal(ops.closing(gap, 1), sq)
    speck = sq.copy()
    speck[2, 2] = 1
    assert np.array_equal(ops.opening(speck, 1), sq)


def test_components_are_numbered_largest_first() -> None:
    a = _square()
    a[2:4, 2:4] = 1  # a small second region
    lab = ops.components(a)
    assert set(np.unique(lab)) == {0, 1, 2}
    assert lab[15, 15] == 1 and lab[2, 2] == 2
    area = ops.area(a)
    assert area[15, 15] == 100 and area[2, 2] == 4 and area[0, 0] == 0
    diagonal = np.eye(5, dtype=np.float32)
    assert np.max(ops.components(diagonal)) == 1  # 8-connected


def test_harris_prefers_corners_to_edges() -> None:
    r = ops.harris(_square(40, 10, 30), 1.5)
    assert np.max(r) == pytest.approx(1.0)
    corner, edge = r[10, 10], r[20, 10]
    assert corner > 0.5 and edge < 0.05


def test_nan_pixels_stay_nan_and_bad_input_is_explained() -> None:
    a = np.ones((10, 10), np.float32)
    a[3, 3] = np.nan
    out = ops.gauss(a, 1)
    assert np.isnan(out[3, 3]) and np.isfinite(out[4, 4])
    with pytest.raises(ValueError, match="one image"):
        ops.gauss(np.ones(5), 1)


def test_kmeans_and_band_math_functions() -> None:
    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal(0, 0.1, (50, 3)), rng.normal(5, 0.1, (50, 3))])
    centres = ops.kmeans(x, 2)
    assert centres[0].mean() < 1 < 4 < centres[1].mean()
    assert set(ops.nearest(x, centres)[:50]) == {0}
    an = NumpyAnalyzer(demo_cube(48, 64, 24))
    k = an.band_math("kmeans(3)")
    assert set(np.unique(k[np.isfinite(k)])) <= {1.0, 2.0, 3.0}
    assert an.band_math("grad(gauss(nm(800), 1)) > otsu(nm(800))").shape == (48, 64)


# --------------------------------------------------------------------------- capture simulations


def test_expose_follows_the_sensor_model() -> None:
    from spektrify.compute import capture as cap

    flat = np.full((200, 200), 0.5, np.float32)
    dn = cap.expose(flat, 1.0)  # 500 electrons on average
    gain = cap.FULL_WELL / 4095
    e_mean, e_std = float(dn.mean()) * gain, float(dn.std()) * gain
    assert abs(e_mean - 500) < 5
    assert abs(e_std - np.sqrt(500 + cap.READ_NOISE**2)) < 2  # shot and read noise add
    assert np.all(cap.expose(flat, 100) == 4095)  # 50,000 electrons: saturated
    assert np.array_equal(cap.expose(flat, 1.0), dn)  # deterministic


def test_defocus_keeps_constants_and_spreads_a_point_into_a_disc() -> None:
    from spektrify.compute import capture as cap

    assert np.allclose(cap.defocus(np.full((20, 20), 2.0, np.float32), 3), 2.0)
    point = np.zeros((31, 31), np.float32)
    point[15, 15] = 1
    psf = cap.defocus(point, 4)
    assert abs(float(psf.sum()) - 1) < 1e-5
    inside = psf[psf > 0]
    assert np.allclose(inside, inside[0])  # flat-topped, not Gaussian
    assert psf[15, 19] > 0 and psf[15, 21] == 0


def test_bayer_round_trip_is_exact_on_smooth_images_and_aliases_fine_detail() -> None:
    from spektrify.compute import capture as cap

    yy, xx = np.mgrid[0:32, 0:32].astype(np.float32)
    r, g, b = 0.1 * xx, 0.05 * yy + 1, np.full_like(xx, 0.3)
    raw = cap.bayer(r, g, b)
    assert raw[0, 0] == r[0, 0] and raw[0, 1] == g[0, 1] and raw[1, 1] == b[1, 1]
    for c, truth in enumerate((r, g, b)):  # bilinear is exact on linear ramps, inside
        assert np.allclose(cap.debayer(raw, c)[2:-2, 2:-2], truth[2:-2, 2:-2], atol=1e-5)
    stripes = (xx % 2).astype(np.float32)  # grey stripes at the Nyquist frequency
    grey = cap.bayer(stripes)
    assert float(np.abs(cap.debayer(grey, 0) - cap.debayer(grey, 2)).mean()) > 0.2


def test_spectral_mosaic_round_trip() -> None:
    from spektrify.compute import capture as cap

    bands = np.arange(16, dtype=np.float32)[:, None, None] * np.ones((16, 24, 32), np.float32)
    frame = cap.mosaic_frame(bands, 4)
    assert frame.shape == (24, 32)
    assert frame[0, 0] == 0 and frame[0, 1] == 1 and frame[1, 0] == 4 and frame[3, 3] == 15
    for i in (0, 5, 15):
        assert np.allclose(cap.demosaic(frame, 4, i), i)


def test_scan_squashes_along_track_and_wobble_shifts_lines() -> None:
    from spektrify.compute import capture as cap

    yy, xx = np.mgrid[0:40, 0:30].astype(np.float32)
    assert np.allclose(cap.scan(yy, 1), yy)
    fast = cap.scan(yy, 2)
    assert np.allclose(fast[:20], 2 * yy[:20]) and np.isnan(fast[20:]).all()
    wobbly = cap.scan(xx, 1, 2)
    assert not np.allclose(wobbly, xx) and np.allclose(
        wobbly[:, 10:20].std(axis=1), xx[0, 10:20].std(), atol=0.5
    )


def test_capture_functions_in_band_math() -> None:
    an = NumpyAnalyzer(demo_cube())
    for expr in (
        "expose(nm(550), 1)",
        "bayer(nm(640), nm(550), nm(465))",
        "mosaic(4)",
        "demosaic(mosaic(4), 4, 3)",
        "debayer(bayer(nm(550)), 1)",
        "scan(nm(800), 1.5)",
        "defocus(nm(550), 2)",
    ):
        assert an.band_math(expr).shape == (192, 256), expr
