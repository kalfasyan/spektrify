# spektrify

A fast, friendly viewer for multispectral and hyperspectral cubes. It runs in your browser
from a local Python process. Scrub through channels, compare spectra, look at the cube in 3D,
and find sensor artefacts and anomalies without writing plotting code.

![Image view](docs/img/image.jpg)

## Install and run

```bash
uv tool install "spektrify[all] @ git+https://github.com/kalfasyan/spektrify"   # or: pip install …

spektrify view cube.h5          # or .npy .npz .mat .tif, ENVI .hdr + data
spektrify view --demo           # a synthetic scene with planted artefacts
spektrify view                  # empty viewer: use the open dialog or drag & drop a file
spektrify learn                 # interactive lessons on spectral imaging (see below)
```

### Example data

```bash
spektrify demo demo.h5          # synthetic 192×256×96 cube with planted artefacts (or .npz)
spektrify demo raw.h5 --raw     # the same scene as a raw 4×4 snapshot mosaic, spektro layout
```

For real close-range scenes, try [ICVL](https://icvl.cs.bgu.ac.il/pages/researches/hyperspectral-imaging.html)
(.mat v7.3 = HDF5, 31 bands, 400–700 nm; open with `--dataset rad`),
[CAVE](https://www.cs.columbia.edu/CAVE/databases/multispectral/) (one PNG per band) or
[Harvard](https://vision.seas.harvard.edu/hyperspec/download.html).

The UI comes prebuilt inside the package, so you don't need Node. The core needs only NumPy.
The extras add more readers: `hdf5` (h5py), `mat` (scipy), `tiff` (tifffile), or `all`.

To use it on a remote GPU box, run `spektrify view cube.h5 --no-browser` there, then
`ssh -L 8765:localhost:8765 box` and open http://localhost:8765.

### Raw sensor data and preprocessing

```bash
spektrify view raw.h5                               # spektro raw mosaic: demosaiced automatically
spektrify view raw.npy --mosaic 4 --demosaic bilinear   # any 2-D mosaic, full resolution
spektrify view cube.hdr -s calibrate:dark=dark.hdr,white=white.hdr -s bin:2
spektrify steps                                     # list steps and their parameters
```

Steps run in order on the loaded cube. The viewer's **Preprocess** panel edits the same
pipeline live (steps that need a file get a Browse button).

| Step | What it does |
| --- | --- |
| `calibrate` | Reflectance from dark and white references (`dark=`, `white=`: number, spectrum or cube file) |
| `flatfield` | Divide out uneven illumination, from a frame (`frame=`) or a smooth surface estimated from the data |
| `whitebalance` | Equalise bands with a gray patch (`x0,y0,x1,y1`), a reference spectrum or gray-world |
| `badpixels` | Repair hot / dead pixels, dead rows and columns, NaN |
| `destripe` | Remove column / row striping (push-broom) |
| `align` | Register bands to a reference band (phase correlation), or apply `shifts=` from a file |
| `smooth` | Savitzky-Golay smoothing along the spectrum; `deriv=1` or `2` for derivatives |
| `snv`, `msc`, `absorbance` | Per-pixel normalisation, scatter correction, −log10(R) |
| `clip`, `crop`, `bands`, `bin` | Per-band percentile cap (as in spektro), crop, band range, pixel binning |

A typical lab order is `badpixels → calibrate → flatfield → align → destripe → smooth / snv`:

```bash
spektrify view cube.h5 -s badpixels -s calibrate:dark=dark.h5,white=white.h5 \
    -s flatfield:frame=flat.tif -s align:max_shift=4 -s snv
```

In Python, call a step directly to pass arrays: `Calibrate(dark=dark_arr, white=white_arr)(cube)`.
Accepted reference files: `.npy`, `.csv` / `.txt` and every cube format; sizes are checked and
mismatches give a clear error.

### Jobs from the shell

```bash
spektrify info cube.h5 --json                 # shape, axis, value range, metadata
spektrify quality cube.h5 --strict            # artefact report; exit code 1 if anything is found
spektrify convert raw.h5 clean.npz -s clip -s bands:2,stop=-2   # preprocess and save
```

### From Python or Jupyter

```python
from spektrify import show, load_cube
from spektrify.preprocess import Pipeline

v = show(cube, wavelengths=wl)   # (H, W, C) or (C, H, W); layout is guessed or pass layout="hwc"
v.update(denoised)               # the open tab switches to the new array
show(cube, inline=True)          # embed in the notebook

clean = Pipeline.parse(["clip", "bin:2"]).apply(load_cube("raw.h5"))
```

## What you can do

| View | For |
| --- | --- |
| **Image** | Band, false-colour RGB, PCA, anomaly (RX, PCA residual, spectral roughness), spectral similarity (SAM), per-pixel stats and band math (`(nm(800) - nm(670)) / (nm(800) + nm(670))`). Histogram stretch with presets, gamma, and highlights for clipped, NaN and defect pixels. |
| **Spectra** | Hover any pixel; click to pin it, or draw rectangles, ellipses and freehand regions (mean ± σ). Views: values, shape, derivative, ratio to a reference, z-score against the scene. CSV export. |
| **Line profile** | Drag a line to see the spectral cross-section along it. |
| **Channels** | Every band as a tile with a crosshair linked across all of them. Misregistration, striping and noisy bands stand out. |
| **3D** | Slice cube with cut planes (the x–λ and y–λ faces show keystone, smile and bad columns), GPU volume rendering (MIP or composite), and pixels as a PCA point cloud. Click a point to pin its pixel. |
| **Quality** | Automatic checks for low SNR, decorrelated bands, column and row striping, dead or hot lines, NaN/Inf and saturation. Every chart links back to the band it is about. |

| **Learn** | A hands-on computer-vision course in 39 lessons, taught on spectral images, from basics (pixels, colour, how cameras and spectral imagers capture images, histograms, thresholds) through intermediate (convolution, edges, Fourier, morphology, calibration) to advanced (features, geometry, clustering, unmixing, classification, evaluation, CNNs, transformers). Each step drives the real viewer; click pixels, find bands, answer quick questions, flip preprocessing Before / After, and follow the reading list from the classic textbooks. |

Press `?` in the app for all keyboard shortcuts. The most used ones: `← →` change band,
`Space` plays through the bands, and `B C P N S M` switch display modes.

| | |
| --- | --- |
| ![Channels](docs/img/channels.jpg) | ![Quality](docs/img/quality.jpg) |
| ![Slice cube](docs/img/cube.jpg) | ![PCA cloud](docs/img/cloud.jpg) |

## Architecture

The project is built so any layer can be replaced without touching the others:

- **Readers and demosaicing** (`spektrify/io`): each file format is one small module registered
  by suffix. Demosaicing methods are registered by name.
- **Preprocessing** (`spektrify/preprocess`): steps are small dataclasses. Registering one makes
  it available in Python, the CLI and the viewer at once.
- **Compute backend** (`spektrify/compute`): an `Analyzer` protocol with a NumPy reference
  implementation. A Rust/PyO3 or GPU version only has to register itself.
- **API** (`spektrify/server/routes.py`): transport-free handlers. The stdlib HTTP adapter is a
  thin shell around them.
- **Lessons** (`spektrify/learn`): plain TOML files validated in Python; the UI runs any of
  them, so adding a lesson needs no code ([docs/learn.md](docs/learn.md)).
- **UI** (`frontend/`): Svelte for panels and state. The WebGL image renderer and the three.js
  3D engine are framework-free modules.

[docs/architecture.md](docs/architecture.md) covers the module boundaries and the API
contract. [CONTRIBUTING.md](CONTRIBUTING.md) covers the dev setup (uv, ruff, ty, pytest, the
UI build), and [docs/releasing.md](docs/releasing.md) covers versions and releases.

## License

GPL-3.0. Bundles [three.js](https://threejs.org) (MIT).
