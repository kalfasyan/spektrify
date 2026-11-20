"""Lessons meet a cube: resolve band references and check the learner's answers.

Lessons are written once but may run on any cube. Where a cube can't express what a task
refers to (no label map for "click the leaf", no wavelengths for "find 720 nm"), the task
turns into free exploration: any answer counts and the feedback says why.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from spektrify.learn.model import BandRef, Lesson, Step, Task
from spektrify.model import Cube

NO_WAVELENGTH_RANGE = (400.0, 1000.0)
"""Where a wavelength reference lands on a cube without wavelengths (as a relative position)."""


def resolve_band(ref: BandRef, cube: Cube) -> int:
    """A band reference → band index on ``cube``: a number is a wavelength (nearest band),
    ``"#12"`` an index and ``"40%"`` a position along the band axis."""
    n = cube.n_bands
    if isinstance(ref, str):
        if ref.startswith("#"):
            return int(np.clip(int(ref[1:]), 0, n - 1))
        return int(np.clip(round(float(ref[:-1]) / 100 * (n - 1)), 0, n - 1))
    if cube.wavelengths is None:
        lo, hi = NO_WAVELENGTH_RANGE
        return int(np.clip(round((float(ref) - lo) / (hi - lo) * (n - 1)), 0, n - 1))
    return int(np.argmin(np.abs(cube.wavelengths - float(ref))))


def labels_of(cube: Cube) -> tuple[np.ndarray, list[str]] | None:
    """The cube's label map and names, if it has a usable one (see ``io.synthetic``)."""
    lab, names = cube.meta.get("labels"), cube.meta.get("label_names")
    if not isinstance(lab, np.ndarray) or not isinstance(names, list):
        return None
    if lab.shape != (cube.height, cube.width):
        return None  # a crop / bin step changed the geometry
    return lab, names


def lesson_json(lesson: Lesson, cube: Cube | None) -> dict[str, Any]:
    """What the UI needs to run ``lesson`` on ``cube``: band references are resolved to
    indices and answers are left out (the server checks them)."""
    return {
        "id": lesson.id,
        "title": lesson.title,
        "summary": lesson.summary,
        "level": lesson.level,
        "unit": lesson.unit,
        "demo": lesson.demo,
        "reading": list(lesson.reading),
        "uses_pipeline": lesson.uses_pipeline,
        "steps": [
            _step_json(s, cube, view, p)
            for s, view, p in zip(
                lesson.steps, _effective_views(lesson), _effective_pipelines(lesson), strict=True
            )
        ],
    }


def _effective_views(lesson: Lesson) -> list[str]:
    """The view at each step: a step without ``view`` keeps the previous one, starting from
    the image view, so a step looks the same however the learner got there."""
    out, current = [], "image"
    for s in lesson.steps:
        current = s.view or current
        out.append(current)
    return out


def _effective_pipelines(lesson: Lesson) -> list[list[dict[str, Any]] | None]:
    """The pipeline in force at each step: a step without ``pipeline`` keeps the previous
    one, and a lesson that sets any starts from the raw cube. Lessons that never set one
    leave the learner's own pipeline alone (``None``)."""
    if not lesson.uses_pipeline:
        return [None] * len(lesson.steps)
    out, current = [], []
    for s in lesson.steps:
        if s.pipeline is not None:
            current = [dict(p) for p in s.pipeline]
        out.append(current)
    return out


def summary_json(lesson: Lesson) -> dict[str, Any]:
    return {
        "id": lesson.id,
        "title": lesson.title,
        "summary": lesson.summary,
        "level": lesson.level,
        "unit": lesson.unit,
        "demo": lesson.demo,
        "steps": len(lesson.steps),
    }


def _step_json(
    step: Step, cube: Cube | None, view: str, pipeline: list[dict[str, Any]] | None
) -> dict[str, Any]:
    show = dict(step.show)
    if cube is not None:
        if "band" in show:
            show["band"] = resolve_band(show["band"], cube)
        if "rgb" in show:
            show["rgb"] = [resolve_band(b, cube) for b in show["rgb"]]
    task = None
    if step.task is not None:
        t = step.task
        task = {"kind": t.kind, "prompt": t.prompt, "hint": t.hint, "options": list(t.options)}
    return {
        "title": step.title,
        "text": step.text,
        "view": view,
        "show": show,
        "pipeline": pipeline,
        "task": task,
    }


def check_answer(task: Task, answer: dict[str, Any], cube: Cube) -> dict[str, Any]:
    """Grade ``answer`` (``{x, y}``, ``{band}`` or ``{choice}``) against ``task``.

    Returns ``{correct, message, note}``; ``note`` explains when the cube can't check it.
    """
    note = None
    if task.kind == "pixel":
        x, y = int(answer["x"]), int(answer["y"])
        if not (0 <= x < cube.width and 0 <= y < cube.height):
            raise ValueError("pixel outside the image")
        lab = labels_of(cube)
        if task.region is None:
            ok = True
        elif lab is None or task.region not in lab[1]:
            ok, note = True, f"This cube has no '{task.region}' label, so any pixel counts."
        else:
            ok = int(lab[0][y, x]) == lab[1].index(task.region)
    elif task.kind == "band":
        b = int(answer["band"])
        if not 0 <= b < cube.n_bands:
            raise ValueError("band out of range")
        assert task.near is not None  # guaranteed by parse_lesson
        if cube.wavelengths is None and isinstance(task.near, (int, float)):
            ok, note = True, "This cube has no wavelengths, so any band counts."
        else:
            target = resolve_band(task.near, cube)
            ax = cube.axis
            ok = abs(float(ax[b]) - float(ax[target])) <= task.tolerance or b == target
    else:
        ok = int(answer["choice"]) == task.answer
    return {"correct": ok, "message": task.success if ok else task.retry, "note": note}
