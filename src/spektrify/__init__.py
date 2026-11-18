"""spektrify: an interactive multi/hyperspectral cube viewer in the browser.

From a shell::

    spektrify cube.h5               # or .npy .npz .mat .hdr (ENVI) .tif
    spektrify --demo                # synthetic cube with planted artifacts

From Python / Jupyter::

    from spektrify import show
    v = show(cube, wavelengths=wl)  # numpy (H, W, C) / (C, H, W), torch, xarray …
    v.update(other_cube)            # swap the data in the open tab
"""

from __future__ import annotations

from typing import Any

from numpy.typing import ArrayLike

from spektrify.io import demo_cube, load_cube
from spektrify.model import Cube
from spektrify.server import Session, ViewerServer

__all__ = ["Cube", "Viewer", "demo_cube", "load_cube", "show", "serve"]


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
        """Replace the displayed cube; the browser tab picks it up automatically."""
        self._server.session.set_cube(_as_cube(array, wavelengths, layout, "array"))

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
            from IPython.display import IFrame, display

            display(IFrame(viewer.url, width="100%", height=height))
        except ImportError:
            inline = False
    if open_browser and not inline:
        import webbrowser

        webbrowser.open(viewer.url)
    return viewer


def serve(
    path: str | None = None,
    *,
    demo: bool = False,
    dataset: str | None = None,
    layout: str = "auto",
    mosaic: int | None = None,
    port: int = 8765,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    """Load ``path`` (or the demo cube) and serve the viewer until interrupted."""
    cube = None
    if demo:
        cube = demo_cube()
    elif path:
        cube = load_cube(path, dataset=dataset, layout=layout, mosaic=mosaic)
    server = ViewerServer(Session(cube), host=host, port=port)
    what = f"{cube.name}  ({cube.height}×{cube.width}×{cube.n_bands})" if cube else "no cube yet"
    print(f"spektrify · {what}\n  → {server.url}   (Ctrl+C to quit)")
    server.serve_forever(open_browser=open_browser)
