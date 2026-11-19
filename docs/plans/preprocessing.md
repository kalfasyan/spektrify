# Plan: more preprocessing methods

Status: implemented (see the PR). Scope: lab / close-range multi- and hyperspectral imaging (no Earth observation).

## Where we start

`spektrify.preprocess` has a step registry (`register_step`, dataclass steps, `Pipeline`) and five
steps: `clip`, `calibrate` (dark/white reference), `crop`, `bands`, `bin`. A step is a frozen
dataclass `Cube -> Cube`. Registering it makes it appear in the Python API, the CLI
(`--step name:k=v`) and the viewer's Preprocess panel, whose form is generated from the schema.
External files already work for `calibrate` through a private helper (`_reference`). This plan
keeps all of that and adds methods, a shared way to load external files, and a small UI upgrade.

## Principles

- One method = one small registered step. No new framework; the registry is the extension point.
- NumPy only in the core (scipy stays optional and is not needed for anything below).
  Numerically heavy parts sit in plain functions in `preprocess/_ops.py` that take and return
  arrays, so they can be swapped for a Rust implementation later without touching step classes,
  the CLI or the UI.
- Steps never mutate their input and record what they did (`cube.meta`) where useful.
- Anything that needs a file takes a path string, the same way in CLI, UI and JSON pipelines.
  In Python you may also pass an array directly.

## Methods: what goes in, what stays out

| Step | Verdict | Why |
| --- | --- | --- |
| `calibrate` (dark + white reference) | Keep, harden | The core of lab imaging. Add `clamp`, a safe divide (`eps`), and use the shared reference loader. |
| `flatfield` | Add | Removes illumination / vignetting / lens falloff with a per-pixel gain. Gain from an external frame or cube (path), or estimated from the data itself (large-scale polynomial fit of the band-mean image) when no file is given. |
| `whitebalance` | Add | Equalise channels using a gray patch (rectangle in the image), a reference spectrum (path), or gray-world. Cheap and very commonly wanted. |
| `badpixels` | Add | Dead/hot pixels and dead lines are the most common sensor artefacts. Detect by residual against a local median (robust MAD threshold) and replace with the local median; also repairs whole dead rows/columns. Reuses what the quality view already shows. |
| `destripe` | Add | Push-broom and line-scan data show column/row striping. Per band, remove column (or row) offsets estimated from the median. Simple and effective. |
| `align` (band registration) | Add, conservative | Genuinely useful for filter-wheel, multi-camera and some mosaic systems. Per-band translation against a reference band using phase correlation on gradient images (robust to the spectral change of brightness), sub-pixel peak refinement, a `max_shift` limit and a confidence check; bands that fail fall back to zero shift. Shifts are stored in `meta["align_shifts"]`. Can instead read shifts from a CSV (path) measured once on a calibration target. Translation only. |
| `smooth` | Add | Savitzky-Golay along the spectral axis with optional 1st/2nd derivative (the standard chemometric pre-step). Window and order are parameters; edges handled by shrinking the window. |
| `snv` | Add | Standard normal variate per pixel spectrum. Removes scatter and brightness. |
| `msc` | Add | Multiplicative scatter correction against the mean spectrum, or an external reference spectrum (path). |
| `absorbance` | Add | `-log10(reflectance)` with a floor; one line and expected after `calibrate`. |
| `continuum` (removal) | Defer | Useful for absorption features but needs convex-hull handling per pixel; not trivial to make fast. Revisit when asked. |
| Spectral resampling / interpolation | Drop | Not a viewer need; users resample upstream. |
| Lens distortion, keystone, smile correction | Drop | Needs per-instrument calibration data and models; we cannot make it generically robust. `align` covers the common translation case. |
| Spatial denoising (median/Gaussian/BM3D), MNF, PCA denoise | Drop | `bin` already trades resolution for noise; PCA is in the viewer; the rest adds weight for unclear benefit. |
| Histogram equalisation / CLAHE | Drop | Display-only; the viewer has stretch controls. Changing data values would be misleading. |
| Demosaicing | Already done | Lives in `io/demosaic.py`. |

## External files

A new `preprocess/references.py` replaces the private `_reference` helper: one loader used by
every step that needs a file.

- `load_reference(spec, cube, kind)` where `kind` is `"spectrum"` (C,), `"image"` (H, W),
  `"cube"` (C, H, W), or `"any"`. `spec` is a number, a path, or (Python API) an array.
- Formats: `.npy`, `.csv`/`.txt` (spectra, shifts), and any cube format the readers support
  (also 2-D `.tif` for flat-field frames). Cubes of the right size are used per pixel; larger or
  differently shaped references are averaged to a spectrum or image where that is meaningful.
- Clear errors for size mismatch (`white.h5: 16 bands, cube has 96`).
- Parameters that hold paths are tagged `path=True` in `param(...)`; the schema exposes
  `"kind": "path"`.

## Surfaces

- **CLI.** Nothing new to learn: `--step flatfield:frame=flat.tif -s calibrate:dark=d.npy,white=w.npy`.
  `spektrify steps` lists the new steps and marks path parameters. A short "recipes" section in the
  README shows the typical order: `badpixels → calibrate → flatfield → align → destripe → smooth/snv`.
- **Python / notebook.** `Pipeline.parse([...]).apply(cube)` as before, or call a step directly:
  `Calibrate(dark=dark_array, white=white_array)(cube)`.
- **UI.** The Preprocess panel already builds forms from the schema, so every new step appears
  with no UI code. One small addition: for parameters marked as paths, a "Browse…" button next to
  the text box opens the existing file browser (reusing the Open dialog) and fills in the path.
  Users who are not frontend developers need nothing more: the built assets are rebuilt and
  committed as for every UI change.

## Delivery

1. `references.py` + move `calibrate` onto it (behaviour unchanged, plus `clamp`/`eps`).
2. Ops + steps: `badpixels`, `flatfield`, `whitebalance`, `destripe`, `smooth`, `snv`, `msc`,
   `absorbance`, `align`. Each with unit tests on synthetic cubes with a known planted defect
   (e.g. shift a band by (3.4, -2.1) px and check the recovered shift to < 0.2 px).
3. Schema `kind: "path"`, UI Browse button, rebuilt static assets.
4. Docs (`architecture.md`, README recipes), CHANGELOG, `ruff`, `ty`, `pytest`.

Acceptance: all checks green; each step has a registry test, a round trip through `Pipeline.parse`,
a numeric test, and an error-path test; `align` has a negative test (random noise bands do not move
bands more than `max_shift`).
