"""Interactive lessons about spectral imaging, run inside the viewer (``spektrify learn``).

Lessons are declarative TOML files (``lessons/*.toml``, format in ``docs/learn.md``): adding
one needs no Python or frontend code. :mod:`.model` parses and validates them,
:mod:`.catalog` finds them, and :mod:`.checks` resolves them against a cube and grades
answers. The HTTP routes in :mod:`spektrify.server.routes` expose all three.
"""

from spektrify.learn.catalog import check_lessons, load_lessons, read_lesson
from spektrify.learn.checks import (
    check_answer,
    labels_of,
    lesson_json,
    resolve_band,
    summary_json,
)
from spektrify.learn.model import LEVELS, Lesson, LessonError, Step, Task, parse_lesson

__all__ = [
    "LEVELS",
    "Lesson",
    "LessonError",
    "Step",
    "Task",
    "check_answer",
    "check_lessons",
    "labels_of",
    "lesson_json",
    "load_lessons",
    "parse_lesson",
    "read_lesson",
    "resolve_band",
    "summary_json",
]
