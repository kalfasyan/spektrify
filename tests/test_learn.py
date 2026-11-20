"""Lessons: file validation, band references, answer checking and the API routes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from spektrify.cli import app
from spektrify.io import DEMOS, demo_capture, demo_cube
from spektrify.learn import (
    LessonError,
    Task,
    check_answer,
    check_lessons,
    labels_of,
    lesson_json,
    load_lessons,
    parse_lesson,
    resolve_band,
)
from spektrify.model import Cube
from spektrify.server.routes import ApiError
from spektrify.server.session import Session

MINIMAL = {"title": "T", "steps": [{"title": "S", "text": "hello"}]}


def test_bundled_lessons_are_valid() -> None:
    assert check_lessons() == []
    lessons = load_lessons()
    assert len(lessons) >= 10
    assert all(le.steps for le in lessons.values())


@pytest.mark.parametrize("lesson_id", list(load_lessons()))
def test_bundled_lesson_targets_exist_in_its_demo(lesson_id: str) -> None:
    """Every region a lesson asks for is labelled in the demo it was written for, and its
    pipelines run on that demo."""
    lesson = load_lessons()[lesson_id]
    cube = DEMOS[lesson.demo or "scene"]()
    lab = labels_of(cube)
    assert lab is not None
    for step in lesson.steps:
        if step.task and step.task.region:
            assert step.task.region in lab[1], (lesson_id, step.title)
    from spektrify.preprocess import Pipeline

    for step in lesson.steps:
        if step.pipeline:
            Pipeline.from_json(step.pipeline).apply(cube)


@pytest.mark.parametrize("lesson_id", list(load_lessons()))
def test_bundled_lesson_band_math_runs_on_its_demo(lesson_id: str) -> None:
    """A typo in a lesson's band-math expression fails here, not in front of a learner."""
    from spektrify.compute.numpy_backend import NumpyAnalyzer

    lesson = load_lessons()[lesson_id]
    an = NumpyAnalyzer(DEMOS[lesson.demo or "scene"]())
    for step in lesson.steps:
        expr = step.show.get("mathExpr")
        if expr:
            out = an.band_math(expr)
            assert np.isfinite(out).any(), (lesson_id, step.title, expr)


def test_catalog_is_ordered_by_level_and_lessons_cite_sources() -> None:
    from spektrify.learn.model import LEVELS

    lessons = list(load_lessons().values())
    levels = [LEVELS.index(le.level) for le in lessons]
    assert levels == sorted(levels)
    assert {le.level for le in lessons} == set(LEVELS)
    assert all(le.unit and le.reading for le in lessons)


def _one_step(**step) -> dict:
    return {"title": "T", "steps": [{"title": "S", **step}]}


def test_parse_errors_name_the_field() -> None:
    with pytest.raises(LessonError, match="needs at least one"):
        parse_lesson({"title": "T", "steps": []}, default_id="x")
    with pytest.raises(LessonError, match=r"steps\[0\]\.show: unknown key 'zoom'"):
        parse_lesson(_one_step(show={"zoom": 2}), default_id="x")
    with pytest.raises(LessonError, match="mode"):
        parse_lesson(_one_step(show={"mode": "x"}), default_id="x")
    with pytest.raises(LessonError, match="pipeline"):
        parse_lesson(
            {"title": "T", "steps": [{"title": "S", "pipeline": [{"name": "nope"}]}]},
            default_id="x",
        )
    bad_choice = {"kind": "choice", "prompt": "?", "options": ["a"], "answer": 0}
    with pytest.raises(LessonError, match="choice"):
        parse_lesson({"title": "T", "steps": [{"title": "S", "task": bad_choice}]}, default_id="x")
    with pytest.raises(LessonError, match="unknown field"):
        parse_lesson({**MINIMAL, "colour": "red"}, default_id="x")
    with pytest.raises(LessonError, match="reading"):
        parse_lesson({**MINIMAL, "reading": [1]}, default_id="x")
    with pytest.raises(LessonError, match="level"):
        parse_lesson({**MINIMAL, "level": "correction"}, default_id="x")
    lesson = parse_lesson({**MINIMAL, "unit": "Filters", "reading": ["A book"]}, default_id="x")
    assert (lesson.unit, lesson.reading) == ("Filters", ("A book",))
    with pytest.raises(LessonError, match="title"):
        parse_lesson({"title": 3, "steps": MINIMAL["steps"]}, default_id="x")


def test_extra_lesson_dir_adds_and_overrides(tmp_path: Path) -> None:
    (tmp_path / "mine.toml").write_text('title = "Mine"\n[[steps]]\ntitle = "Hi"\n')
    (tmp_path / "cube.toml").write_text('id = "cube"\ntitle = "Replaced"\n[[steps]]\ntitle = "x"\n')
    lessons = load_lessons([tmp_path])
    assert lessons["mine"].title == "Mine"
    assert lessons["cube"].title == "Replaced"
    (tmp_path / "broken.toml").write_text("title = \n")
    assert any("broken.toml" in e for e in check_lessons([tmp_path]))


def test_resolve_band() -> None:
    cube = demo_cube(16, 16, 11)  # 450 … 950 nm in 50 nm steps
    assert resolve_band(700, cube) == 5
    assert resolve_band("#3", cube) == 3
    assert resolve_band("#99", cube) == 10
    assert resolve_band("50%", cube) == 5
    no_wl = Cube(cube.data)
    assert resolve_band(400, no_wl) == 0 and resolve_band(1000, no_wl) == 10


def test_pixel_task_uses_labels_and_degrades_without_them() -> None:
    cube = demo_cube()
    task = Task("pixel", "Click the leaf", region="leaf")
    assert check_answer(task, {"x": 80, "y": 95}, cube)["correct"]
    assert not check_answer(task, {"x": 250, "y": 5}, cube)["correct"]
    plain = Cube(cube.data, cube.wavelengths)
    r = check_answer(task, {"x": 250, "y": 5}, plain)
    assert r["correct"] and "no 'leaf' label" in r["note"]
    cropped = cube.with_data(cube.data[:, :50, :50])  # stale label map is ignored
    assert labels_of(cropped) is None
    with pytest.raises(ValueError):
        check_answer(task, {"x": 999, "y": 0}, cube)


def test_band_and_choice_tasks() -> None:
    cube = demo_cube()
    task = Task("band", "Find the red edge", near=715, tolerance=20)
    assert check_answer(task, {"band": resolve_band(720, cube)}, cube)["correct"]
    assert not check_answer(task, {"band": 0}, cube)["correct"]
    assert check_answer(task, {"band": 0}, Cube(cube.data))["note"]
    quiz = Task("choice", "?", options=("a", "b"), answer=1, success="yes", retry="no")
    ok = {"correct": True, "message": "yes", "note": None}
    assert check_answer(quiz, {"choice": 1}, cube) == ok
    assert check_answer(quiz, {"choice": 0}, cube)["message"] == "no"


def test_lesson_json_resolves_bands_hides_answers_and_carries_pipelines() -> None:
    lessons = load_lessons()
    cube = demo_cube()
    j = lesson_json(lessons["composites"], cube)
    assert j["steps"][0]["show"]["rgb"] == [resolve_band(b, cube) for b in (640, 550, 465)]
    assert all("answer" not in (s["task"] or {}) for s in j["steps"])
    cal = lesson_json(lessons["calibration"], demo_capture())
    pipes = [s["pipeline"] for s in cal["steps"]]
    assert pipes[0] == [] and len(pipes[1]) == 1 and pipes[-1] == pipes[-2]
    pca = lesson_json(lessons["pca"], cube)["steps"]
    assert all(s["pipeline"] is None for s in pca)
    assert [s["view"] for s in pca] == ["image", "image", "image", "3d"]


def test_demo_labels_match_geometry() -> None:
    cube = demo_cube()
    lab, names = labels_of(cube) or (None, [])
    assert lab is not None and lab.shape == (cube.height, cube.width)
    assert lab[95, 80] == names.index("leaf")
    assert (lab[:, 37] == names.index("dead_column")).all()
    cap = demo_capture()
    assert "white_tile" in cap.meta["label_names"]
    assert float(np.min(cap.data)) > 50  # raw counts sit on a dark level
    assert "labels" not in cube.json_meta()  # arrays stay server-side


def test_routes(call) -> None:
    s = Session(demo_cube())
    listing = call(s, "lessons").obj
    assert listing["demo"] == "scene" and listing["labelled"]
    assert {le["id"] for le in listing["lessons"]} >= {"cube", "calibration"}
    lesson = call(s, "lesson", id="cube").obj
    assert lesson["steps"][1]["task"]["kind"] == "pixel"
    r = call(s, "lesson-check", "POST", {"id": "cube", "step": 1, "answer": {"x": 80, "y": 95}})
    assert r.obj["correct"]
    with pytest.raises(ApiError):
        call(s, "lesson-check", "POST", {"id": "cube", "step": 3, "answer": {}})  # no task
    with pytest.raises(ApiError):
        call(s, "lesson-check", "POST", {"id": "cube", "step": 1, "answer": {}})
    with pytest.raises(ApiError):
        call(s, "lesson", id="nope")
    call(s, "demo", "POST", {"name": "capture"})
    assert s.cube is not None and s.cube.meta["demo"] == "capture"
    with pytest.raises(ApiError):
        call(s, "demo", "POST", {"name": "nope"})


def test_cli_learn_check(tmp_path: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["learn", "--check"])
    assert r.exit_code == 0 and "lessons OK" in r.output
    (tmp_path / "bad.toml").write_text('title = "x"\n')
    r = runner.invoke(app, ["learn", "--check", "--lessons", str(tmp_path)])
    assert r.exit_code == 1
