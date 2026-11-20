# Learn mode and writing lessons

`spektrify learn` opens the viewer with a lesson panel on the left. The bundled lessons form a
course in computer vision taught on spectral images, in three levels:

- **Basics**: digital images, cubes and wavelengths, colour and metamers, intensity
  transforms, histograms, band math, thresholds, comparing materials.
- **Intermediate**: convolution, noise and median filters, edges, sharpening, the Fourier
  domain, sampling and pyramids, morphology, regions, and cleaning raw data (sensor
  problems, calibration, band alignment, repairs, spectral pre-treatments).
- **Advanced**: local features, cameras, multi-view geometry, PCA, clustering, unmixing,
  anomaly detection, classification, evaluation, convolutional networks, modern
  architectures and a capstone on engineering practice.

Each lesson ends with further reading (Gonzalez & Woods, Szeliski, Torralba, Isola & Freeman,
Prince, Hartley & Zisserman, Ma et al., Bishop, Goodfellow et al. and the original papers).
The plan behind it is in [plans/learn-curriculum.md](plans/learn-curriculum.md).

Each lesson is a short sequence of steps; every step explains one idea and drives the real viewer next to it (switching
the view, the bands on screen, a preprocessing pipeline) and can ask the learner to do something:
click a pixel, find a band or answer a question. The server checks the answer and the panel
gives instant feedback.

```bash
spektrify learn                      # the built-in demo scene
spektrify learn --demo capture       # the same scene as raw camera counts
spektrify learn cube.h5              # your own cube
spektrify learn --lessons my-lessons/   # add (or replace) lessons
spektrify learn --check --lessons my-lessons/   # validate lesson files and exit
```

The **Learn** button in the top bar opens the same panel from `spektrify view`.

## Demo cubes

Both demos are generated in code (`spektrify/io/synthetic.py`), so they ship with the package
and have no licence questions. They share one scene: a leaf, two kinds of discs and a tiny
target with a narrow 760 nm peak.

| Name | Contents |
| --- | --- |
| `scene` | Reflectance with planted defects: dead column, striped band, noisy band, saturated pixels, NaN patch, vignetting. Same as `spektrify view --demo`. |
| `capture` | Raw counts: dark level 100, halogen-lamp × sensor response, stronger vignetting, a white reference tile, bands misregistered by up to ±2 px. |

Each demo carries a label map (`meta["labels"]`, `meta["label_names"]`): `background`, `leaf`,
`pill_a` (upper discs), `pill_b` (lower discs), `target`, and per demo `dead_column`,
`hot_pixels`, `nan_patch` or `white_tile`. A pixel task names one of these.

## Lessons on your own cube

Lessons run on whatever cube is open. Band references resolve to the nearest band of that cube.
When a cube can't check a task (it has no label map, or no wavelengths for a "find 720 nm"
task), the task accepts any answer and the feedback says why. Lessons written for a demo say so
in the panel, with a button to load it.

## The lesson file format

One lesson is one [TOML](https://toml.io) file. Bundled lessons live in
`src/spektrify/learn/lessons/`; the file name only sets the order on disk.

```toml
id = "red-edge"                 # optional; default is the file name without .toml
title = "The red edge"
summary = "One line shown in the lesson list."
level = "basics"                # basics | intermediate | advanced (the list's groups)
unit = "Images and spectra"     # optional: subheading within the level
order = 25                      # position within the level (units follow the order)
demo = "scene"                  # optional: the built-in cube this lesson is written for
reading = [                     # optional: shown when the lesson ends (Markdown)
  "Gonzalez & Woods, *Digital Image Processing* (4th ed.), ch. 6.",
]

[[steps]]
title = "Pin the leaf"
text = """
Markdown subset: paragraphs, - lists, **bold**, *italic*, `code`, [links](https://…).
"""
view = "image"                  # image | grid | 3d | quality (default: keep the previous one)
show = { mode = "rgb", rgb = [640, 550, 465], specView = "values" }

[steps.task]
kind = "pixel"
region = "leaf"
prompt = "Click the leaf."
hint = "The large shape on the left."
success = "That's its spectrum below."
retry = "Not the leaf. Try again."
```

### `show`: what the viewer displays

| Key | Value |
| --- | --- |
| `mode` | `band`, `rgb`, `pca`, `anomaly`, `similarity`, `summary`, `math` |
| `band` | a band reference (below) |
| `rgb` | three band references, red / green / blue |
| `pcaOffset`, `pcaAsRgb` | first component shown; three components as RGB |
| `anomaly`, `anomalyK`, `anomalyTop` | `rx`, `residual` or `gradient`; components for `residual`; % of top scores highlighted |
| `simDeg` | spectral-angle threshold in degrees |
| `summary` | `mean`, `std`, `max`, `argmax`, `invalid` |
| `mathExpr` | band-math expression, e.g. `(nm(800) - nm(670)) / (nm(800) + nm(670))` (functions below) |
| `specView`, `specMean`, `specStd`, `specLog` | spectrum plot: `values`, `normalized`, `derivative`, `ratio`, `zscore`; overlays |
| `cmap` | colour map name |

A **band reference** is a number (a wavelength in the cube's units, nearest band), `"#12"` (a
band index) or `"40%"` (a position along the band axis). On a cube without wavelengths, a
number maps 400 to 1000 nm onto the band axis.

### Image functions in band math

Band math (in lessons and in the viewer's band-math box) can call these on any image, such
as `nm(670)` or `b[4]`. They live in `spektrify/compute/imageops.py` (plain NumPy).

| Group | Functions |
| --- | --- |
| Point operations | `stretch(x, lo=2, hi=98)`, `quantize(x, levels)`, `equalize(x)`, `otsu(x)` (a threshold value), `subsample(x, f)` |
| Filters | `box(x, r)`, `gauss(x, sigma)`, `median(x, r)` (r ≤ 3) |
| Derivatives | `dx(x)`, `dy(x)` (Sobel), `grad(x)`, `laplace(x)` |
| Frequency | `fft(x)` (log magnitude, centred), `lowpass(x, cutoff)`, `highpass(x, cutoff)` (cutoff as a fraction of the highest frequency) |
| Morphology | `erode(x, r)`, `dilate(x, r)`, `opening(x, r)`, `closing(x, r)` (square of side 2r + 1) |
| Regions | `components(mask)` (1 = largest, 8-connected), `area(mask)` |
| Features | `harris(x, sigma=1.5)` (scaled so the strongest corner is 1) |
| Whole cube | `kmeans(k)`: cluster map of every pixel's spectrum, 1..k from darkest |
| Test patterns | `x`, `y` (pixel column and row), `sin`, `cos`, e.g. the zone plate `cos(((x - 128)**2 + (y - 96)**2) / 150)` |

A test runs every bundled lesson's expression on its demo, so a typo fails CI.

### `pipeline`: preprocessing with Before / After

```toml
pipeline = [
  { name = "calibrate", params = { dark = "100" } },
  { name = "flatfield" },
]
```

Any registered preprocessing step works (`spektrify steps` lists them); parameters left out use
their defaults. The panel shows a **Before / After** switch, and pins keep their place so their
spectra can be compared. A step without `pipeline` keeps the previous step's. A lesson that
sets a pipeline anywhere starts from the raw cube, and the learner's own pipeline comes back
when they leave the lesson. `pipeline = []` shows the raw cube.

### `task`: what the learner does

| `kind` | Fields | Correct when |
| --- | --- | --- |
| `pixel` | `region` (optional label name) | the clicked pixel has that label (any pixel if no `region`) |
| `band` | `near` (band reference), `tolerance` (axis units, default 10) | the band shown is within `tolerance` of `near` |
| `choice` | `options` (2 or more), `answer` (index from 0) | the chosen option is `answer` |

All tasks take `prompt`, and optionally `hint`, `success` and `retry` messages. Tasks never
block: the learner can always skip ahead.

## How it fits together

```
lessons/*.toml ─► learn.catalog ─► learn.model (validate) ─┐
                                                           ├─► routes: GET lessons, GET lesson, POST lesson-check
cube (labels, wavelengths) ─► learn.checks (resolve, grade)┘
                                       frontend: lib/learn.svelte.js ─► components/learn/LearnPanel.svelte
```

- `learn/model.py` parses a file into frozen dataclasses and reports every mistake with its
  location (`lesson.toml: steps[2].show.mode: …`).
- `learn/checks.py` resolves band references for the cube on display, carries views and
  pipelines forward, and grades answers. Answers never reach the browser.
- The frontend applies a step through the same store and controller the rest of the viewer
  uses. It has no knowledge of any particular lesson.

The API:

| Method | Endpoint | Returns |
| --- | --- | --- |
| GET | `lessons` | `{lessons: [{id, title, summary, level, unit, demo, steps}], demo, labelled}` |
| GET | `lesson?id=` | The lesson resolved for the current cube (band indices, effective view and pipeline per step, tasks without answers) |
| POST | `lesson-check` | Body `{id, step, answer: {x, y} \| {band} \| {choice}}` → `{correct, message, note}` |
| POST | `demo` | Body `{name: "scene" \| "capture"}`: show a built-in cube |
