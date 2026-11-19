"""Finding and loading lesson files (``*.toml``): the bundled ones plus any extra folders."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from spektrify.learn.model import LEVELS, Lesson, LessonError, parse_lesson

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib  # ty: ignore[import-not-found]

BUNDLED = Path(__file__).resolve().parent / "lessons"


def read_lesson(path: str | Path) -> Lesson:
    """Parse and validate one lesson file."""
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise LessonError(f"{path}: {e}") from e
    return parse_lesson(data, default_id=path.stem, source=str(path))


def lesson_files(dirs: Iterable[str | Path] = ()) -> list[Path]:
    """The bundled lesson files followed by those in ``dirs`` (a file path is taken as is)."""
    out = sorted(BUNDLED.glob("*.toml"))
    for d in dirs:
        d = Path(d).expanduser()
        if not d.exists():
            raise FileNotFoundError(d)
        out += [d] if d.is_file() else sorted(d.glob("*.toml"))
    return out


def load_lessons(dirs: Iterable[str | Path] = ()) -> dict[str, Lesson]:
    """All lessons by id, in teaching order. A lesson in ``dirs`` replaces a bundled one
    with the same id, so you can override a bundled lesson by copying and editing it."""
    found: dict[str, Lesson] = {}
    for path in lesson_files(dirs):
        lesson = read_lesson(path)
        found[lesson.id] = lesson
    ordered = sorted(found.values(), key=lambda le: (LEVELS.index(le.level), le.order, le.title))
    return {le.id: le for le in ordered}


def check_lessons(dirs: Iterable[str | Path] = ()) -> list[str]:
    """Validate every lesson file; returns one message per problem (empty = all good)."""
    errors = []
    seen: dict[str, Path] = {}
    for path in lesson_files(dirs):
        try:
            lesson = read_lesson(path)
        except LessonError as e:
            errors.append(str(e))
            continue
        if lesson.id in seen and seen[lesson.id].parent == path.parent:
            errors.append(f"{path}: id {lesson.id!r} is also used by {seen[lesson.id]}")
        seen[lesson.id] = path
    return errors
