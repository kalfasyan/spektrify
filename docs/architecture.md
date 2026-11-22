# Architecture

spektrify has four layers. Each one talks to the next only through a small, documented
contract, so any of them can be rewritten (in Rust, on the GPU, in another UI framework)
without touching the rest.

```
 file ──► io ──► Cube ──► preprocess ──► Cube ──► compute ──► server/routes ──► HTTP ──► frontend
          register_reader  register_step           register_backend  dispatch()  http.py  Svelte
          register_demosaicer                                          ▲
                                                             cli.py ───┘ (info / quality / convert / demo)
```

## Python package (`src/spektrify`)

| Module | Role | Depends on |
| --- | --- | --- |
| `model.py` | `Cube`: band-major float32 `(C, H, W)` data, wavelengths or band axis, name, source, metadata. `Cube.from_array()` guesses `hwc` / `chw`. | numpy |
| `io/` | One reader per format. `base.py` defines `Reader` (`suffixes`, `read(path, *, dataset)` → `RawArray`) and the registry. `load_cube()` picks a reader by suffix, applies layout and demosaicing. `synthetic.py` makes the demo cubes (`DEMOS`: the `scene` and a raw `capture`), each with a label map for the lessons. `writers.py` saves cubes (`save_cube`) and raw mosaics (`save_raw_mosaic`). | model |
| `io/demosaic.py` | Snapshot-mosaic demosaicing methods by name: `block` (one pixel per macropixel) and `bilinear` (full resolution, co-registered channels). `mosaic()` is the inverse of `block`. | numpy |
| `preprocess/` | `base.py`: the step registry (`register_step`, `param`, `step_schema`) and `Pipeline` (parse CLI specs, JSON round trip, `apply`). `steps.py`: `clip`, `calibrate`, `crop`, `bands`, `bin`. `corrections.py`: `badpixels`, `flatfield`, `whitebalance`, `destripe`, `align`. `spectral.py`: `smooth`, `snv`, `msc`, `absorbance`. `references.py`: the one loader for external files (dark / white, flat frames, spectra, shifts). `_ops.py`: the array kernels behind the steps as plain NumPy functions, so any of them can be replaced by a faster implementation. Steps never mutate their input. | model, io |
| `learn/` | Interactive lessons. `lessons/*.toml` are the content; `model.py` validates a file into frozen dataclasses; `catalog.py` loads the bundled lessons plus extra folders; `checks.py` resolves band references for a cube and grades answers (answers never reach the browser). Format: [learn.md](learn.md). | preprocess, model |
| `compute/` | `base.py` defines the `Analyzer` protocol (stats, quality, PCA, RX, SAM, band math, regions, line profiles, 3-D data). `numpy_backend.py` is the reference implementation. `bandmath.py` is a whitelisted AST evaluator (no `eval`); `imageops.py` holds the image functions it can call (filters, edges, FFT, morphology, regions, Harris, k-means), plain NumPy and replaceable one function at a time. `regions.py` rasterises UI shapes to masks. | model |
| `server/session.py` | The raw cube, the preprocessing pipeline, the lesson catalog, the cube on display (raw → pipeline), its analyzer, a product cache and a `generation` counter (bumped on every swap so open tabs reload). Thread-safe. | compute, preprocess |
| `server/routes.py` | The whole HTTP API as plain functions `(Session, Request) → Json | Binary`, registered with `@route`. `dispatch()` is the only entry point. No HTTP types here. | session, io |
| `server/snapshot.py` | Saves the API's responses for every state the lessons reach (demo cube × pipeline) to static files, for the online demo ([site.md](site.md)). Calls `dispatch()` like any transport; answer keys come from running `check_answer` over every possible answer. | routes, learn |
| `server/http.py` | stdlib `ThreadingHTTPServer` adapter: static files, error mapping, binary headers. Swap it for FastAPI / aiohttp / a desktop shell by calling `dispatch()`. | routes |
| `__init__.py` | Public Python API: `show()`, `serve()`, `Viewer.update()`, `Viewer.stop()`. | everything |
| `cli.py` | The `spektrify` command (Typer): `view`, `learn`, `info`, `quality`, `convert`, `demo`, `steps`. Imports are lazy so `--help` is instant. | everything |
| `_json.py` | Strict JSON encoding (NaN → `null`, numpy types) shared by the API and the CLI. | numpy |

Heavy optional libraries (h5py, scipy, tifffile) are imported inside the reader that needs
them, so `import spektrify` stays light and the core needs only NumPy.

### Adding a file format

```python
# spektrify/io/myformat_io.py
from spektrify.io.base import RawArray, register_reader

class MyReader:
    suffixes = (".xyz",)
    def read(self, path, *, dataset=None) -> RawArray:
        arr, wl = ...                      # any (H, W, C) / (C, H, W) array
        return RawArray(arr, wl, layout="hwc")

register_reader(MyReader())
```

Import it in `io/__init__.py`, and the open dialog, drag and drop, and CLI pick it up.

### Adding a preprocessing step

```python
from dataclasses import dataclass
from spektrify.preprocess import param, register_step

@register_step("scale", "Multiply by a constant.")
@dataclass(frozen=True)
class Scale:
    k: float = param(2.0, "Factor.")

    def __call__(self, cube):
        return cube.with_data(cube.data * self.k)
```

Mark a parameter that names a file with `param(default, help, path=True)`: the schema then
reports `kind: "path"` and the Preprocess panel adds a Browse button. Load it with the helpers in
`spektrify.preprocess.references` (`per_band`, `spectrum`, `image`), so every step accepts the same
formats and gives the same errors.

It then works as `--step scale:3`, in `Pipeline.parse(["scale:3"])`, and in the viewer's
Preprocess panel (the form is generated from the parameters and their help texts).

### Replacing the compute backend

Implement the `Analyzer` protocol (`compute/base.py`) and register a factory:

```python
from spektrify.compute import register_backend
register_backend("rust", lambda cube: RustAnalyzer(cube))
Session(cube, backend="rust")
```

Array conventions: maps are `(H, W)` or `(k, H, W)` float32 with NaN for invalid pixels,
and spectra are `(C,)`. The tests in `tests/test_viewer.py` describe the expected behaviour
and work as a conformance suite for a new backend.

## HTTP API

All endpoints are under `/api/`. JSON responses are strict JSON: NaN and Inf become `null`.
Binary responses are raw little-endian arrays with an `X-Meta` JSON header
`{"dtype": "float32", "shape": [...], ...}`.

| Method | Endpoint | Returns |
| --- | --- | --- |
| GET | `meta` | Cube description: dims, axis, unit, per-band mean/std, global percentiles, mean spectrum, current pipeline |
| GET | `generation` | `{generation}`; changes when the cube is swapped |
| GET | `band?i=` | Binary `(H, W)` |
| GET | `thumbs?side=` | Binary `(C, h, w)` block-mean thumbnails |
| GET | `spectrum?x=&y=` | `{x, y, values}` |
| POST | `region` | Body `{kind: rect\|ellipse\|poly, …}`. Returns `{n, mean, std, min, max, p05, p95}` |
| GET | `slice?axis=row\|col&i=` | Binary `(C, W)` or `(C, H)` cross-section |
| GET | `line?x0=&y0=&x1=&y1=` | Binary `(n, C)` |
| GET/POST | `product?kind=` | Binary `(k, H, W)`. Kinds: `pca` (`k`, `offset`), `rx`, `residual`, `sam` (body `reference`), `gradient`, `mean`, `std`, `max`, `argmax`, `invalid`, `math` (body `expr`) |
| GET | `quality` | Per-band SNR, neighbour correlation, striping, NaN and saturation fractions, flags, line defects, findings |
| GET | `correlation` | Binary `(C, C)` |
| GET | `stripes?which=columns\|rows` | Binary `(C, W)` or `(C, H)` line-artefact scores in noise σ |
| GET | `volume?max=` | Binary `(C', H', W')` uint8 downsampled volume |
| GET | `scatter?n=` | Binary uint32: `n×3` float32 PCA scores (bit-cast) followed by `n` pixel indices |
| GET | `browse?dir=` | Directory listing filtered to supported formats, plus recent files |
| POST | `open` | Body `{path, dataset?, layout?, mosaic?, demosaic?, steps?}` |
| GET | `steps` | Preprocessing step schemas and demosaic method names |
| POST | `pipeline` | Body `{steps: [{name, params}]}`; re-processes the raw cube |
| POST | `upload?name=&layout=` | Raw file body (ENVI: send `.hdr` and data as two uploads) |
| POST | `transpose` | Body `{order}` to fix a wrong axis guess |
| POST | `demo` | Body `{name}`: show a built-in demo cube (`scene`, `capture`) |
| GET | `lessons` / `lesson?id=` | Lesson catalog; one lesson resolved for the current cube |
| POST | `lesson-check` | Body `{id, step, answer}` → `{correct, message, note}` |

The server binds to `127.0.0.1` by default. It serves the local filesystem to the browser
(through the open dialog), so don't expose it on a public interface.

## Frontend (`frontend/`)

Svelte 5 handles panels, controls and state. Anything that draws a lot is a plain JS
"engine" with no framework dependency, so it can be reused or rewritten on its own.

```
src/
  lib/
    api.js                 fetch wrappers (JSON + binary); the transport is the server or,
                           in the site build, static/backend.js
    static/                online demo backend: answers /api/ from the snapshot files, with
                           per-pixel reads (spectra, regions, slices, SAM) in cubeops.js
    store.svelte.js        app state ($state) + band cache, layer resolution, stretch, marks
    controller.svelte.js   actions the UI performs; wires store changes to engines
    shortcuts.js           one table drives both key handling and the help dialog
    engines/               framework-free: imageView (WebGL2), view3d (three.js), spectrumPlot,
                           histogram, scrubber, lineProfile, qualityCharts
    gl/imageRenderer.js    float textures, LUTs, clip / NaN / threshold highlighting in GLSL
    learn.svelte.js        Learn mode: applies lesson steps through the store / controller
    markdown.js            tiny, HTML-escaping Markdown subset for lesson text
  components/              TopBar, StatusBar, image/*, dialogs/*, learn/LearnPanel
  views/                   ChannelsView, ThreeView (lazy-loads three.js), QualityView
```

How data flows: components call `ctl.*` or `store.set(...)`. The store emits the changed keys.
The controller reacts by refreshing the current layer and pushing it to the engines that
registered with `ctl.attach(name, engine)`. Engines emit events (`hover`, `band`, `region`, …)
back to the controller.

### Rebuilding the UI

```bash
cd frontend
npm install
npm run dev     # with `spektrify view --demo --no-browser` running; Vite proxies /api to :8765
npm run build   # writes ../src/spektrify/static — commit it so pip users never need Node
npm run build:site   # the online demo's UI into ../build/site (scripts/build-site.sh adds the data)
```
