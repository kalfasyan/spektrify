"""Lessons as plain data: parsing and validating the content files.

A lesson is a list of steps. Each step has text, optionally sets what the viewer shows
(``view``, ``show``), optionally runs a preprocessing ``pipeline`` (with a Before/After
toggle in the UI) and optionally asks the learner to do something (``task``). The file
format is documented in ``docs/learn.md``; this module only turns a parsed mapping into
frozen dataclasses and reports every mistake with its location.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from spektrify.preprocess import Pipeline

LEVELS = ("basics", "intermediate", "advanced")
"""Lesson levels, in the order the catalog lists them. Within a level, ``unit`` names a
group of related lessons (a subheading in the list)."""

VIEWS = ("image", "grid", "3d", "quality")
MODES = ("band", "rgb", "pca", "anomaly", "similarity", "summary", "math")
TASK_KINDS = ("pixel", "band", "choice")

# Diagrams a step can show above its text: kind -> {option: allowed values}. ``list`` means a
# list of names. Each kind is a Svelte component in ``frontend/src/components/learn/figures/``
# (a test keeps both lists in sync); the first value of an option is its default.
# ``none`` hides the diagram carried over from an earlier step.
FIGURES: dict[str, dict[str, tuple[str, ...] | type]] = {
    "none": {},
    "cube": {"focus": ("stack", "band", "pixel", "rgb")},
    "pixels": {"show": ("values", "levels", "coarse", "neighbours", "threshold", "histogram")},
    "kernel": {"op": ("box", "gauss", "median", "dx", "laplace", "erode", "dilate", "corner")},
    "tone": {"curve": ("linear", "log", "gamma", "stretch")},
    "spectrum": {"show": ("sample", "absorb", "edge", "compare", "angle", "smooth", "snv")},
    "pipeline": {"steps": list},
    "scatter": {"show": ("pca", "kmeans", "boundary", "overfit", "metrics", "anomaly", "unmix")},
    "waves": {"show": ("sum", "alias", "filter")},
    "camera": {"show": ("pinhole", "lens", "pushbroom", "epipolar")},
    "layers": {"show": ("cnn", "resnet", "unet", "attention")},
    "sensor": {"show": ("photons", "counts", "shot", "saturate")},
    "mosaic": {"show": ("bayer", "spectral")},
}

# Viewer state a step may set, with the type each value must have. Band references (``band``,
# ``rgb``) are resolved per cube by :mod:`spektrify.learn.checks`.
SHOW_KEYS: dict[str, type | tuple[type, ...]] = {
    "mode": str,
    "band": (int, float, str),
    "rgb": list,
    "pcaOffset": int,
    "pcaAsRgb": bool,
    "anomaly": str,
    "anomalyK": int,
    "anomalyTop": (int, float),
    "simDeg": (int, float),
    "summary": str,
    "mathExpr": str,
    "specView": str,
    "specMean": bool,
    "specStd": bool,
    "specLog": bool,
    "cmap": str,
}

BandRef = int | float | str
"""A band: a number is a wavelength (axis units), ``"#12"`` an index, ``"40%"`` a position."""


class LessonError(ValueError):
    """A lesson file is malformed; the message says where."""


@dataclass(frozen=True)
class Task:
    kind: str
    prompt: str
    hint: str = ""
    success: str = "Correct!"
    retry: str = "Not quite. Try again."
    region: str | None = None  # pixel: label name the click must land on
    near: BandRef | None = None  # band: the band to find
    tolerance: float = 10.0  # band: how far off (axis units) still counts
    options: tuple[str, ...] = ()  # choice
    answer: int | None = None  # choice: index into options


@dataclass(frozen=True)
class Step:
    title: str
    text: str
    view: str | None = None
    show: Mapping[str, Any] = field(default_factory=dict)
    pipeline: tuple[Mapping[str, Any], ...] | None = None
    task: Task | None = None
    figure: Mapping[str, Any] | None = None  # {kind, ...options}; see FIGURES


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    summary: str
    steps: tuple[Step, ...]
    level: str = "basics"
    unit: str = ""  # subheading within the level, e.g. "Filters"
    order: int = 100
    demo: str | None = None  # built-in cube the lesson is written for (None = any cube)
    reading: tuple[str, ...] = ()  # references shown when the lesson ends (Markdown)
    source: str = ""

    @property
    def uses_pipeline(self) -> bool:
        return any(s.pipeline is not None for s in self.steps)


# --------------------------------------------------------------------------- parsing


def parse_lesson(data: Mapping[str, Any], *, default_id: str, source: str = "") -> Lesson:
    """Validate a parsed lesson file. Raises :class:`LessonError` naming the bad field."""
    where = source or default_id
    _known(
        data,
        {"id", "title", "summary", "level", "unit", "order", "demo", "reading", "steps"},
        where,
    )
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise LessonError(f"{where}: needs at least one [[steps]] table")
    level = _get(data, "level", str, where, "basics")
    if level not in LEVELS:
        raise LessonError(f"{where}: level must be one of {', '.join(LEVELS)}")
    reading = _get(data, "reading", list, where, [])
    if not all(isinstance(r, str) for r in reading):
        raise LessonError(f"{where}.reading: must be a list of strings")
    return Lesson(
        id=_get(data, "id", str, where, default_id),
        title=_get(data, "title", str, where),
        summary=_get(data, "summary", str, where, ""),
        level=level,
        unit=_get(data, "unit", str, where, ""),
        order=_get(data, "order", int, where, 100),
        demo=_get(data, "demo", str, where, None),
        reading=tuple(reading),
        steps=tuple(_step(s, f"{where}: steps[{i}]") for i, s in enumerate(steps)),
        source=source,
    )


def _step(d: Any, where: str) -> Step:
    if not isinstance(d, Mapping):
        raise LessonError(f"{where}: must be a table")
    _known(d, {"title", "text", "view", "show", "pipeline", "task", "figure"}, where)
    view = _get(d, "view", str, where, None)
    if view is not None and view not in VIEWS:
        raise LessonError(f"{where}.view: must be one of {', '.join(VIEWS)}")
    show = _get(d, "show", dict, where, {})
    for k, v in show.items():
        if k not in SHOW_KEYS:
            raise LessonError(f"{where}.show: unknown key {k!r} (allowed: {', '.join(SHOW_KEYS)})")
        if (isinstance(v, bool) and SHOW_KEYS[k] is not bool) or not isinstance(v, SHOW_KEYS[k]):
            raise LessonError(f"{where}.show.{k}: wrong type {type(v).__name__}")
    if "mode" in show and show["mode"] not in MODES:
        raise LessonError(f"{where}.show.mode: must be one of {', '.join(MODES)}")
    if "rgb" in show and (len(show["rgb"]) != 3 or not all(_is_ref(b) for b in show["rgb"])):
        raise LessonError(f"{where}.show.rgb: needs three band references")
    if "band" in show and not _is_ref(show["band"]):
        raise LessonError(f"{where}.show.band: not a band reference")
    pipeline = d.get("pipeline")
    if pipeline is not None:
        try:
            pipeline = tuple(Pipeline.from_json(pipeline).to_json())
        except (KeyError, TypeError, ValueError) as e:
            raise LessonError(f"{where}.pipeline: {e}") from e
    task = d.get("task")
    return Step(
        title=_get(d, "title", str, where),
        text=_get(d, "text", str, where, "").strip(),
        view=view,
        show=show,
        pipeline=pipeline,
        task=None if task is None else _task(task, f"{where}.task"),
        figure=_figure(d.get("figure"), f"{where}.figure"),
    )


def _figure(d: Any, where: str) -> Mapping[str, Any] | None:
    if d is None:
        return None
    if not isinstance(d, Mapping):
        raise LessonError(f'{where}: must be a table like {{ kind = "cube" }}')
    kind = _get(d, "kind", str, where)
    if kind not in FIGURES:
        raise LessonError(f"{where}.kind: must be one of {', '.join(FIGURES)}")
    options = FIGURES[kind]
    _known(d, {"kind", *options}, where)
    for k, allowed in options.items():
        if k not in d:
            continue
        v = d[k]
        if isinstance(allowed, tuple) and v not in allowed:
            raise LessonError(f"{where}.{k}: must be one of {', '.join(allowed)}")
        if allowed is list and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise LessonError(f"{where}.{k}: must be a list of names")
    defaults = {k: v[0] for k, v in options.items() if isinstance(v, tuple)}
    return {**defaults, **d}


def _task(d: Any, where: str) -> Task:
    if not isinstance(d, Mapping):
        raise LessonError(f"{where}: must be a table")
    _known(
        d,
        {"kind", "prompt", "hint", "success", "retry", "region", "near", "tolerance"}
        | {"options", "answer"},
        where,
    )
    kind = _get(d, "kind", str, where)
    if kind not in TASK_KINDS:
        raise LessonError(f"{where}.kind: must be one of {', '.join(TASK_KINDS)}")
    options = tuple(_get(d, "options", list, where, []))
    answer = _get(d, "answer", int, where, None)
    near = d.get("near")
    if kind == "choice" and (len(options) < 2 or answer is None or not 0 <= answer < len(options)):
        raise LessonError(f"{where}: a choice needs 2+ options and an answer index into them")
    if kind == "band" and not _is_ref(near):
        raise LessonError(f"{where}.near: a band task needs the band to find")
    defaults = Task(kind, "")
    return Task(
        kind=kind,
        prompt=_get(d, "prompt", str, where),
        hint=_get(d, "hint", str, where, ""),
        success=_get(d, "success", str, where, defaults.success),
        retry=_get(d, "retry", str, where, defaults.retry),
        region=_get(d, "region", str, where, None),
        near=near,
        tolerance=float(_get(d, "tolerance", (int, float), where, defaults.tolerance)),
        options=tuple(str(o) for o in options),
        answer=answer,
    )


def _is_ref(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and (
        (v.startswith("#") and v[1:].isdigit()) or (v.endswith("%") and _is_float(v[:-1]))
    )


def _is_float(s: str) -> bool:
    try:
        float(s)
    except ValueError:
        return False
    return True


def _known(d: Mapping[str, Any], allowed: set[str], where: str) -> None:
    extra = sorted(set(d) - allowed)
    if extra:
        raise LessonError(f"{where}: unknown field(s) {', '.join(extra)}")


_REQUIRED = object()


def _get(
    d: Mapping[str, Any],
    key: str,
    typ: type | tuple[type, ...],
    where: str,
    default: Any = _REQUIRED,
) -> Any:
    if key not in d:
        if default is _REQUIRED:
            raise LessonError(f"{where}: missing {key!r}")
        return default
    v = d[key]
    if (isinstance(v, bool) and typ is not bool) or not isinstance(v, typ):
        raise LessonError(f"{where}.{key}: expected {_type_name(typ)}, got {type(v).__name__}")
    return v


def _type_name(typ: type | tuple[type, ...]) -> str:
    return " or ".join(t.__name__ for t in (typ if isinstance(typ, tuple) else (typ,)))
