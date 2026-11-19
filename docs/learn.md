# Learn mode and writing lessons

`spektrify learn` opens the viewer with a lesson panel on the left. Each lesson is a short
sequence of steps; every step explains one idea and drives the real viewer next to it (switching
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
level = "basics"                # basics | correction | analysis (the list's groups)
order = 25                      # position within the group
demo = "scene"                  # optional: the built-in cube this lesson is written for

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
| `mathExpr` | band-math expression, e.g. `(nm(800) - nm(670)) / (nm(800) + nm(670))` |
| `specView`, `specMean`, `specStd`, `specLog` | spectrum plot: `values`, `normalized`, `derivative`, `ratio`, `zscore`; overlays |
| `cmap` | colour map name |

A **band reference** is a number (a wavelength in the cube's units, nearest band), `"#12"` (a
band index) or `"40%"` (a position along the band axis). On a cube without wavelengths, a
number maps 400 to 1000 nm onto the band axis.

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
| GET | `lessons` | `{lessons: [{id, title, summary, level, demo, steps}], demo, labelled}` |
| GET | `lesson?id=` | The lesson resolved for the current cube (band indices, effective view and pipeline per step, tasks without answers) |
| POST | `lesson-check` | Body `{id, step, answer: {x, y} \| {band} \| {choice}}` → `{correct, message, note}` |
| POST | `demo` | Body `{name: "scene" \| "capture"}`: show a built-in cube |
