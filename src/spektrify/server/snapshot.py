"""Freeze the viewer's API into static files, so learn mode can run without a server.

The online demo (``frontend``'s ``site`` build, deployed to a static host) cannot run
Python. Instead this module drives the real API through :func:`~spektrify.server.routes.dispatch`
for every demo cube, every pipeline the lessons use and every request the lessons make, and
writes the responses to disk. The browser's static backend (``frontend/src/lib/static/``)
answers the UI from these files, plus a few cheap per-pixel reads (spectra, slices, regions,
spectral angle) that it computes from the shipped cube.

Nothing here knows about any single lesson: requests come from the lesson files, and answer
checking is precomputed by running :func:`~spektrify.learn.check_answer` over every possible
answer. Run it with ``python -m spektrify.server.snapshot OUT_DIR``.

Layout of ``OUT_DIR``::

    index.json              lesson summaries, step schemas, the states and the start demo
    lessons/<id>.json       a lesson resolved for its demo, plus ``checks`` (answer keys)
    s<N>/state.json         one (demo, pipeline) state: JSON responses and binary file index
    s<N>/*.zbin             arrays as gzip-compressed byte planes, see :func:`pack`
                            (``cube.zbin`` is the displayed cube as float16)
"""

from __future__ import annotations

import base64
import gzip
import json
import shutil
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy as np

from spektrify._json import dumps
from spektrify.io import DEMOS, demosaic_methods
from spektrify.learn import Lesson, Task, check_answer, lesson_json, summary_json
from spektrify.model import Cube
from spektrify.preprocess import Pipeline, step_schema
from spektrify.server.routes import Binary, Json, Request, dispatch
from spektrify.server.session import Session

FORMAT = 1
"""Bumped when the layout changes; the browser refuses a snapshot it doesn't understand."""

START_DEMO = "scene"

# What the UI asks for, with the parameters it sends (see frontend/src/lib/store.svelte.js
# and engines/view3d.js). Keep in step with those call sites.
VOLUME = {"max": "192"}
SCATTER = {"n": "50000"}
UI_DEFAULTS: dict[str, Any] = {
    "view": "image",
    "mode": "band",
    "pcaOffset": 0,
    "pcaAsRgb": True,
    "anomaly": "rx",
    "anomalyK": 3,
    "summary": "mean",
    "mathExpr": "",
}
SUMMARIES = ("mean", "std", "max", "argmax", "invalid")


# --------------------------------------------------------------------------- requests


@dataclass(frozen=True)
class Call:
    """One GET request to the API, keyed exactly as the browser keys it."""

    name: str
    params: tuple[tuple[str, str], ...] = ()

    @staticmethod
    def of(name: str, **params: Any) -> Call:
        return Call(name, tuple(sorted((k, str(v)) for k, v in params.items())))

    @property
    def key(self) -> str:
        return f"{self.name}?{urlencode(self.params)}" if self.params else self.name


def pipeline_key(steps: list[dict[str, Any]] | None) -> str:
    """Canonical text of a pipeline; the browser computes the same (sorted keys, no spaces)."""
    return json.dumps(steps or [], sort_keys=True, separators=(",", ":"))


@dataclass
class StateSpec:
    """Everything to record for one (demo, pipeline) state."""

    demo: str
    pipeline: list[dict[str, Any]]
    calls: set[Call] = field(default_factory=set)
    exprs: set[str] = field(default_factory=set)
    checks: list[tuple[Lesson, int]] = field(default_factory=list)

    @property
    def id(self) -> tuple[str, str]:
        return self.demo, pipeline_key(self.pipeline)


def core_calls() -> set[Call]:
    """What every cube needs beyond the cube itself (the browser derives thumbnails)."""
    return {
        Call.of("correlation"),
        Call.of("stripes", which="columns"),
        Call.of("stripes", which="rows"),
    }


def explore_calls(n_bands: int) -> set[Call]:
    """The analysis views a learner may open on a demo cube outside any lesson."""
    calls = {Call.of("volume", **VOLUME), Call.of("scatter", **SCATTER)}
    calls |= {Call.of("product", kind="pca", k=3, offset=o) for o in range(max(1, n_bands - 2))[:3]}
    calls |= {Call.of("product", kind="pca", k=1, offset=o) for o in range(n_bands)[:5]}
    calls |= {Call.of("product", kind=k) for k in ("rx", "gradient", *SUMMARIES)}
    calls |= {Call.of("product", kind="residual", k=k) for k in range(1, min(n_bands, 6))}
    return calls


def layer_calls(ui: dict[str, Any], n_bands: int) -> tuple[set[Call], set[str]]:
    """The requests the UI makes to show ``ui`` (the display state after a lesson step)."""
    calls: set[Call] = set()
    exprs: set[str] = set()
    if ui["view"] == "3d":
        calls |= {Call.of("volume", **VOLUME), Call.of("scatter", **SCATTER)}
    mode = ui["mode"]
    if mode == "pca":
        k = 3 if ui["pcaAsRgb"] else 1
        calls.add(Call.of("product", kind="pca", k=k, offset=min(ui["pcaOffset"], n_bands - k)))
    elif mode == "anomaly":
        kind = ui["anomaly"]
        calls.add(
            Call.of("product", kind=kind, k=ui["anomalyK"])
            if kind == "residual"
            else Call.of("product", kind=kind)
        )
    elif mode == "summary":
        calls.add(Call.of("product", kind=ui["summary"]))
    elif mode == "math" and ui["mathExpr"].strip():
        exprs.add(ui["mathExpr"])
    return calls, exprs


def demo_of(lesson: Lesson) -> str:
    """The demo a lesson runs on online (the UI starts lessons without one on the scene)."""
    return lesson.demo or START_DEMO


def plan(lessons: Iterable[Lesson]) -> list[StateSpec]:
    """Every state the lessons can reach, and what to record in each."""
    states: dict[tuple[str, str], StateSpec] = {}

    def state(demo: str, pipeline: list[dict[str, Any]] | None) -> StateSpec:
        spec = StateSpec(demo, [dict(p) for p in pipeline or []])
        return states.setdefault(spec.id, spec)

    bands = {name: make().n_bands for name, make in DEMOS.items()}
    for name in DEMOS:
        state(name, []).calls |= core_calls() | explore_calls(bands[name])
    for lesson in lessons:
        demo = demo_of(lesson)
        resolved = lesson_json(lesson, None)
        ui = dict(UI_DEFAULTS)
        for i, (step, rstep) in enumerate(zip(lesson.steps, resolved["steps"], strict=True)):
            ui |= {k: v for k, v in step.show.items() if k in UI_DEFAULTS}
            ui["view"] = rstep["view"]
            st = state(demo, rstep["pipeline"])
            st.calls |= core_calls()
            calls, exprs = layer_calls(ui, bands[demo])
            st.calls |= calls
            st.exprs |= exprs
            if step.task is not None:
                st.checks.append((lesson, i))
    return list(states.values())


# --------------------------------------------------------------------------- answers


def answer_key(task: Task, cube: Cube) -> dict[str, Any]:
    """Grade every possible answer once: distinct results plus one result index per answer
    (pixel tasks: row-major over the image; band tasks: per band; choices: per option).

    A pixel's grade only depends on its label, so pixel tasks call the grader once per
    label value and spread the result over the image.
    """
    outcomes: list[dict[str, Any]] = []
    seen: dict[str, int] = {}

    def code(result: dict[str, Any]) -> int:
        text = json.dumps(result, sort_keys=True)
        if text not in seen:
            seen[text] = len(outcomes)
            outcomes.append(result)
        return seen[text]

    if task.kind == "pixel":
        labels = cube.meta.get("labels")
        if isinstance(labels, np.ndarray) and labels.shape == (cube.height, cube.width):
            codes = np.zeros(labels.shape, dtype=np.uint8)
            for value in np.unique(labels):
                y, x = (int(v[0]) for v in np.nonzero(labels == value))
                codes[labels == value] = code(check_answer(task, {"x": x, "y": y}, cube))
        else:
            only = code(check_answer(task, {"x": 0, "y": 0}, cube))
            codes = np.full((cube.height, cube.width), only, dtype=np.uint8)
        packed = base64.b64encode(codes.tobytes()).decode()
        return {"kind": "pixel", "width": cube.width, "outcomes": outcomes, "codes": packed}
    if task.kind == "band":
        answers = [{"band": b} for b in range(cube.n_bands)]
    else:
        answers = [{"choice": c} for c in range(len(task.options))]
    codes_list = [code(check_answer(task, a, cube)) for a in answers]
    return {"kind": task.kind, "outcomes": outcomes, "codes": codes_list}


# --------------------------------------------------------------------------- writing


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(obj), encoding="utf-8")


def pack(arr: np.ndarray) -> bytes:
    """Little-endian bytes split into byte planes (all first bytes, then all second bytes…),
    gzip-compressed. Planes compress far better than interleaved floats, and static hosts
    rarely compress binary files themselves."""
    arr = np.ascontiguousarray(arr, dtype=arr.dtype.newbyteorder("<"))
    planes = arr.view(np.uint8).reshape(-1, arr.dtype.itemsize).T
    return gzip.compress(np.ascontiguousarray(planes).tobytes(), compresslevel=9, mtime=0)


def _write_array(path: Path, arr: np.ndarray, meta: dict[str, Any]) -> dict[str, Any]:
    arr = np.asarray(arr)
    path.write_bytes(pack(arr))
    return {"file": path.name, "meta": {**meta, "dtype": str(arr.dtype), "shape": list(arr.shape)}}


def _get(session: Session, call: Call) -> Json | Binary:
    params = {k: [v] for k, v in call.params}
    return dispatch(session, "GET", call.name, Request(params=params))


def record_state(spec: StateSpec, out: Path) -> dict[str, Any]:
    """Run the API for one state and write its responses to ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    session = open_state(spec)
    cube, _ = session.require()
    state: dict[str, Any] = {"json": {}, "bin": {}, "math": {}}
    for name in ("meta", "quality"):
        res = _get(session, Call.of(name))
        assert isinstance(res, Json)
        state["json"][name] = res.obj
    state["cube"] = _write_array(out / "cube.zbin", cube.data.astype(np.float16), {})
    for n, call in enumerate(sorted(spec.calls, key=lambda c: c.key)):
        res = _get(session, call)
        assert isinstance(res, Binary), call.key
        state["bin"][call.key] = _write_array(out / f"b{n}.zbin", res.array, res.meta)
    for n, expr in enumerate(sorted(spec.exprs)):
        req = Request(params={"kind": ["math"]}, body={"expr": expr})
        res = dispatch(session, "POST", "product", req)
        assert isinstance(res, Binary)
        arr = np.asarray(res.array, dtype=np.float32)
        state["math"][expr] = _write_array(out / f"m{n}.zbin", arr, res.meta)
    _write_json(out / "state.json", state)
    return state


def open_state(spec: StateSpec) -> Session:
    session = Session()
    session.set_cube(DEMOS[spec.demo](), Pipeline.from_json(spec.pipeline))
    return session


def build(out: Path, lesson_dirs: Iterable[str | Path] = ()) -> dict[str, Any]:
    """Write the whole snapshot to ``out`` (emptied first) and return its index."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    lessons = Session(lesson_dirs=lesson_dirs).lessons()
    specs = plan(lessons.values())

    states = []
    for n, spec in enumerate(specs):
        d = f"s{n}"
        state = record_state(spec, out / d)
        # The UI asks by the lesson's pipeline or by the one the server reported back.
        keys = {pipeline_key(spec.pipeline), pipeline_key(state["json"]["meta"]["pipeline"])}
        states.append({"demo": spec.demo, "pipelines": sorted(keys), "dir": d})

    checks: dict[str, dict[str, Any]] = {lid: {} for lid in lessons}
    for spec in specs:
        if not spec.checks:
            continue
        cube, _ = open_state(spec).require()
        for lesson, i in spec.checks:
            task = lesson.steps[i].task
            assert task is not None
            checks[lesson.id][str(i)] = answer_key(task, cube)

    demo_cubes = {name: make() for name, make in DEMOS.items()}
    for lid, lesson in lessons.items():
        _write_json(
            out / "lessons" / f"{lid}.json",
            {**lesson_json(lesson, demo_cubes[demo_of(lesson)]), "checks": checks[lid]},
        )

    index = {
        "format": FORMAT,
        "start": START_DEMO,
        "lessons": [summary_json(le) for le in lessons.values()],
        "steps": {"steps": step_schema(), "demosaic": demosaic_methods()},
        "states": states,
    }
    _write_json(out / "index.json", index)
    return index


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: python -m spektrify.server.snapshot OUT_DIR")
    out = Path(args[0])
    index = build(out)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    n_states, n_lessons = len(index["states"]), len(index["lessons"])
    print(f"{n_states} states, {n_lessons} lessons, {size / 1e6:.1f} MB in {out}")


if __name__ == "__main__":
    main()
