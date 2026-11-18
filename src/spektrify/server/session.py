"""Server-side state: the cube on display, its analyzer and a small product cache."""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spektrify.compute import Analyzer, create_analyzer
from spektrify.model import Cube


class Session:
    """The cube currently on display plus its cached analyses.

    ``generation`` increments whenever the cube changes so clients can detect swaps
    (e.g. :meth:`spektrify.Viewer.update` from a notebook).
    """

    def __init__(self, cube: Cube | None = None, backend: str = "numpy") -> None:
        self._lock = threading.RLock()
        self.backend = backend
        self.generation = 0
        self.cube: Cube | None = None
        self.analyzer: Analyzer | None = None
        self.recent: list[str] = []
        self._cache: dict[str, Any] = {}
        self._upload_dir: Path | None = None
        if cube is not None:
            self.set_cube(cube)

    def set_cube(self, cube: Cube) -> None:
        with self._lock:
            self.cube = cube
            self.analyzer = create_analyzer(cube, self.backend)
            self._cache.clear()
            self.generation += 1
            if cube.source:
                if cube.source in self.recent:
                    self.recent.remove(cube.source)
                self.recent.insert(0, cube.source)
                del self.recent[12:]

    def require(self) -> tuple[Cube, Analyzer]:
        with self._lock:
            if self.cube is None or self.analyzer is None:
                raise LookupError("No cube loaded")
            return self.cube, self.analyzer

    def cached(self, key: str, fn: Callable[[], Any]) -> Any:
        """Memoise ``fn()`` for the current cube (bounded, oldest evicted first)."""
        gen = self.generation
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit
        res = fn()
        with self._lock:
            if gen == self.generation:
                if len(self._cache) > 24:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = res
        return res

    def upload_dir(self) -> Path:
        if self._upload_dir is None:
            self._upload_dir = Path(tempfile.mkdtemp(prefix="spektrify-"))
        return self._upload_dir

    def default_dir(self) -> Path:
        if self.cube is not None and self.cube.source:
            return Path(self.cube.source).parent
        return Path.cwd()
