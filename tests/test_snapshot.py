"""The static snapshot behind the online demo: planning, packing and precomputed grading."""

from __future__ import annotations

import base64
import gzip
import json

import numpy as np
import pytest

from spektrify.io import DEMOS
from spektrify.learn import check_answer, load_lessons
from spektrify.server.snapshot import (
    Call,
    StateSpec,
    answer_key,
    demo_of,
    open_state,
    pack,
    pipeline_key,
    plan,
    record_state,
)


def unpack(data: bytes, dtype: str) -> np.ndarray:
    """What the browser does in frontend/src/lib/static/files.js."""
    raw = np.frombuffer(gzip.decompress(data), np.uint8)
    size = np.dtype(dtype).itemsize
    return raw.reshape(size, -1).T.copy().view(np.dtype(dtype).newbyteorder("<")).ravel()


@pytest.mark.parametrize("dtype", ["float32", "float16", "uint8", "uint32"])
def test_pack_round_trip(dtype):
    arr = (np.arange(60).reshape(3, 4, 5) * 1.5).astype(dtype)
    assert np.array_equal(unpack(pack(arr), dtype), arr.ravel())


def test_call_keys_match_the_browser():
    # The browser sorts the query parameters and URL-encodes them the same way.
    assert Call.of("product", offset=0, kind="pca", k=3).key == "product?k=3&kind=pca&offset=0"
    assert Call.of("correlation").key == "correlation"
    assert pipeline_key([{"params": {"b": 1, "a": "x y"}, "name": "s"}]) == (
        '[{"name":"s","params":{"a":"x y","b":1}}]'
    )


@pytest.fixture(scope="module")
def lessons():
    return load_lessons()


@pytest.fixture(scope="module")
def states(lessons):
    return plan(lessons.values())


def test_plan_covers_every_lesson(lessons, states):
    by_id = {s.id: s for s in states}
    assert {(name, "[]") for name in DEMOS} <= set(by_id)
    exprs = set().union(*(s.exprs for s in states))
    tasks = {(le.id, i) for s in states for le, i in s.checks}
    for lesson in lessons.values():
        for i, step in enumerate(lesson.steps):
            if "mathExpr" in step.show:
                assert step.show["mathExpr"] in exprs, (lesson.id, i)
            if step.task is not None:
                assert (lesson.id, i) in tasks
            if step.pipeline is not None:
                assert (demo_of(lesson), pipeline_key(step.pipeline)) in by_id


def test_answer_keys_agree_with_the_grader(lessons, states):
    rng = np.random.default_rng(0)
    for spec in states:
        cube, _ = open_state(spec).require()
        for lesson, i in spec.checks:
            task = lesson.steps[i].task
            assert task is not None
            key = answer_key(task, cube)
            if key["kind"] == "pixel":
                codes = np.frombuffer(base64.b64decode(key["codes"]), np.uint8)
                for _ in range(40):
                    x, y = int(rng.integers(cube.width)), int(rng.integers(cube.height))
                    got = key["outcomes"][codes[y * key["width"] + x]]
                    assert got == check_answer(task, {"x": x, "y": y}, cube), (lesson.id, i)
            else:
                field = "band" if key["kind"] == "band" else "choice"
                for a, code in enumerate(key["codes"]):
                    assert key["outcomes"][code] == check_answer(task, {field: a}, cube)
            assert any(o["correct"] for o in key["outcomes"]), (lesson.id, i)


def test_record_state(tmp_path):
    spec = StateSpec(
        "photo", [], {Call.of("correlation"), Call.of("product", kind="rx")}, {"b[0] * 2"}
    )
    state = record_state(spec, tmp_path)
    assert set(state["json"]) == {"meta", "quality"}
    assert json.loads((tmp_path / "state.json").read_text())["math"].keys() == {"b[0] * 2"}
    cube = DEMOS["photo"]()
    entry = state["cube"]
    shipped = unpack((tmp_path / entry["file"]).read_bytes(), entry["meta"]["dtype"])
    assert entry["meta"]["shape"] == list(cube.data.shape)
    assert np.allclose(shipped.astype(np.float32), cube.data.ravel(), rtol=1e-3, atol=1e-4)
    math = state["math"]["b[0] * 2"]
    result = unpack((tmp_path / math["file"]).read_bytes(), math["meta"]["dtype"])
    assert np.allclose(result, (cube.data[0] * 2).ravel())
