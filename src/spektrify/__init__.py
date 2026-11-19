"""spektrify: an interactive multi/hyperspectral cube viewer in the browser.

From a shell::

    spektrify view cube.h5          # or .npy .npz .mat .hdr (ENVI) .tif
    spektrify view --demo           # synthetic cube with planted artifacts
    spektrify quality cube.h5       # artefact report (``--json``, ``--strict`` for CI)
    spektrify learn                 # interactive lessons on spectral imaging

From Python / Jupyter::

    from spektrify import show
    v = show(cube, wavelengths=wl)  # numpy (H, W, C) / (C, H, W), torch, xarray …
    v.update(other_cube)            # swap the data in the open tab
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from numpy.typing import ArrayLike

from spektrify.io import demo_cube, load_cube
from spektrify.model import Cube
from spektrify.server import Session, ViewerServer

__all__ = ["Cube", "Viewer", "__version__", "demo_cube", "load_cube", "serve", "show"]

try:
    __version__ = version("spektrify")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.0.0+unknown"


class Viewer:
    """Handle to a viewer running in a background thread."""

    def __init__(self, server: ViewerServer) -> None:
        self._server = server

    @property
    def url(self) -> str:
        return self._server.url

    def update(
        self, array: ArrayLike | Cube, wavelengths: ArrayLike | None = None, *, layout: str = "auto"
    ) -> None:
        """Replace the displayed cube (keeping the preprocessing pipeline); the browser tab
        picks it up automatically."""
        session = self._server.session
        session.set_cube(_as_cube(array, wavelengths, layout, "array"), session.pipeline)

    def stop(self) -> None:
        self._server.stop()

    def _repr_html_(self) -> str:
        return (
            f'<a href="{self.url}" target="_blank">spektrify</a> running at <code>{self.url}</code>'
        )

    def __repr__(self) -> str:
        return f"Viewer(url={self.url!r})"


def _as_cube(array: Any, wavelengths: Any, layout: str, name: str) -> Cube:
    if isinstance(array, Cube):
        return array
    return Cube.from_array(array, wavelengths, layout=layout, name=name)


def show(
    array: ArrayLike | Cube | None = None,
    wavelengths: ArrayLike | None = None,
    *,
    layout: str = "auto",
    name: str = "array",
    port: int = 8765,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    inline: bool = False,
    height: int = 820,
) -> Viewer:
    """Open the viewer on an in-memory array without blocking.

    ``layout`` is ``"auto"``, ``"hwc"`` or ``"chw"``. With ``inline=True`` (Jupyter) the
    viewer is embedded below the cell instead of opening a browser tab.
    """
    cube = None if array is None else _as_cube(array, wavelengths, layout, name)
    server = ViewerServer(Session(cube), host=host, port=port).start()
    viewer = Viewer(server)
    if inline:
        try:
            from IPython.display import IFrame, display  # ty: ignore[import-not-found]

            display(IFrame(viewer.url, width="100%", height=height))
        except ImportError:
            inline = False
    if open_browser and not inline:
        import webbrowser

        webbrowser.open(viewer.url)
    return viewer


def serve(
    cube: Cube | None = None,
    *,
    port: int = 8765,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    learn: bool = False,
    lesson_dirs: Iterable[str | Path] = (),
) -> None:
    """Serve the viewer on ``cube`` (or an empty viewer) until interrupted. Blocks.

    ``learn=True`` opens the lesson panel; ``lesson_dirs`` adds folders of lesson files.
    """
    server = ViewerServer(Session(cube, lesson_dirs=lesson_dirs), host=host, port=port)
    what = f"{cube.name}  ({cube.height}×{cube.width}×{cube.n_bands})" if cube else "no cube yet"
    url = server.url + ("#learn" if learn else "")
    print(f"spektrify · {what}\n  → {url}   (Ctrl+C to quit)")
    server.serve_forever(open_browser=open_browser, page="#learn" if learn else "")
