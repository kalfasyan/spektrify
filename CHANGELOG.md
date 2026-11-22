# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/): the version comes from the git tag (`vX.Y.Z`).

## [Unreleased]

First release (to be tagged `v0.1.0`).

### Added
- Learn mode has a new look: a warm, paper-like reading panel (light, dark, or following
  the system; switch in the panel header), short step-by-step lessons, and an animated
  diagram above each step with play, step and frame controls. Twelve diagram kinds (spectral
  cube, pixel grid, sliding 3 × 3 window, tone curve, spectra, preprocessing pipeline,
  feature-space scatter, waves, camera geometry and lenses, network layers, sensor wells,
  filter mosaics) are chosen per step with `figure = { kind = "…" }` in a lesson file; 38
  of the 39 bundled lessons use them. `,` and `.`
  step through a lesson. On phones the panel sits above the viewer.
- Learn mode gains an early unit, **How images are captured** (5 lessons in Basics): light
  and what a pixel measures (photons, silicon, QE, counts), exposure, noise and dynamic range,
  lenses, focus and blur (f-number, defocus, diffraction, aberrations, vignetting), colour
  filter arrays and demosaicing (Bayer, false colour, moiré, spectral mosaics), and how
  spectral cameras capture a cube (whisk-broom, push-broom, filter / tunable, snapshot). The
  advanced *Cameras and image formation* lesson now covers the push-broom camera model
  instead of repeating them.
- Band math can simulate capture: `expose`, `defocus`, `bayer`, `debayer`, `mosaic(t)`,
  `demosaic` and `scan` (module `compute/capture.py`).
- A third demo, `photo`: a real public-domain photo (NASA, via scikit-image) as a 3-band
  cube in linear light (`spektrify learn --demo photo`).
- Learn mode is a computer-vision course: 34 lessons in three levels (basics,
  intermediate, advanced), grouped into units, from digital images and histograms through
  filters, Fourier, morphology and calibration to features, multi-view geometry, clustering,
  unmixing, classification, evaluation, CNNs and transformers. Lessons take `unit` and
  `reading` (shown when a lesson ends); levels are now `basics | intermediate | advanced`.
- Band math can call image functions (`gauss`, `median`, `grad`, `fft`, `lowpass`,
  `erode`, `opening`, `components`, `area`, `otsu`, `equalize`, `harris`, `kmeans(k)` and
  more; see `docs/learn.md`), from the new pure-NumPy module `compute/imageops.py`, plus
  `x`, `y`, `sin` and `cos` for test patterns.
- The demo leaf has a chlorophyll absorption dip near 675 nm, as real leaves do.
- Learn mode (`spektrify learn`, or the **Learn** button): 12 interactive lessons on spectral
  imaging, from what a cube is to calibration, band alignment, preprocessing, PCA and anomaly
  detection. Steps drive the real viewer, ask for a pixel, a band or a multiple-choice answer
  (graded by the server), and show preprocessing Before / After. Lessons are TOML files
  (`docs/learn.md`); `--lessons DIR` adds your own and `--check` validates them.
- A second built-in demo, `capture`: the demo scene as raw camera counts (dark level, lamp
  spectrum, vignetting, white reference tile, misregistered bands). Both demos carry a label
  map. `POST /api/demo` switches between them.
- Applying a preprocessing pipeline keeps the zoom, display settings and pins when the image
  size doesn't change.
- Browser-based viewer: band / RGB / PCA / anomaly / similarity / stats / band-math display,
  spectra and line profiles, all-channels grid, 3D slice cube, volume rendering and PCA
  cloud, and a data-quality dashboard.
- Readers for .npy / .npz, HDF5, MATLAB, TIFF and ENVI, including spektro's raw mosaic HDF5
  files (the macropixel size is inferred from the number of filters).
- Demosaicing methods for snapshot-mosaic sensors: `block` (as in spektro) and `bilinear`
  (full sensor resolution, channels co-registered).
- Preprocessing pipeline with registered, composable steps: `clip` (spektro's per-band
  percentile clipper), `calibrate` (dark / white reference), `crop`, `bands`, `bin`. Usable
  from Python (`Pipeline`), the CLI (`--step`) and the viewer's Preprocess panel.
- More preprocessing steps for lab / close-range imaging: `badpixels` (hot / dead pixels,
  dead rows and columns, NaN), `flatfield` (from a frame or estimated), `whitebalance`
  (gray patch, reference spectrum or gray-world), `destripe`, `align` (per-band registration by
  phase correlation, or shifts from a file), `smooth` (Savitzky-Golay, optional derivative),
  `snv`, `msc` and `absorbance`. `calibrate` gained `clamp` and `eps`.
- External files for calibration steps (dark / white references, flat-field frames, reference
  spectra, alignment shifts) are loaded by one shared loader (`spektrify.preprocess.references`)
  from `.npy`, `.csv` / `.txt` or any cube format; in Python an array can be passed directly.
  The Preprocess panel shows a Browse button for these parameters.
- Command line built with Typer: `spektrify view | info | quality | convert | demo | steps`,
  with `--json` output and `quality --strict` (exit code 1 on issues) for scripts and CI.
- `spektrify demo` writes an example cube with planted artefacts to .h5 / .npz, or with
  `--raw` a spektro-style 4×4 mosaic HDF5 to try demosaicing on.
- Writers: `save_cube()` (.npz / .h5, H×W×C + wavelengths), `save_raw_mosaic()` and
  `mosaic()` (the inverse of block demosaicing).
- Python API: `show()` / `Viewer.update()` for notebooks, `serve()`, `load_cube()`.
- uv project with a lock file, ruff, ty type checking, pytest with coverage. CI on Linux,
  macOS and Windows (Python 3.10–3.13), a wheel smoke test, and a tag-driven release workflow
  (GitHub release, optional PyPI trusted publishing).

[Unreleased]: https://github.com/kalfasyan/spektrify/commits/main
