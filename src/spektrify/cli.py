"""The ``spektrify`` command line: open the viewer, or run quick jobs on a cube from a shell."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

if TYPE_CHECKING:
    from spektrify.model import Cube

app = typer.Typer(
    name="spektrify",
    help="Multi/hyperspectral cube viewer and quick-look tools.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)


class Layout(str, Enum):
    auto = "auto"
    hwc = "hwc"
    chw = "chw"


# Arguments and options shared by every command that reads a cube.
_CUBE_HELP = "Cube file: .npy .npz .h5 .mat .tif or ENVI .hdr"
CubePath = Annotated[Path, typer.Argument(help=_CUBE_HELP, dir_okay=False)]
OptionalCubePath = Annotated[Path | None, typer.Argument(help=_CUBE_HELP, dir_okay=False)]
Dataset = Annotated[str | None, typer.Option(help="Array name inside a container file.")]
LayoutOpt = Annotated[Layout, typer.Option(help="Axis order of the stored array.")]
Mosaic = Annotated[int | None, typer.Option(help="Demosaic a 2-D mosaic (macropixel size).")]
Demosaic = Annotated[
    str, typer.Option(help="Demosaic method: block (fast) or bilinear (full resolution).")
]
Steps = Annotated[
    list[str] | None,
    typer.Option(
        "--step",
        "-s",
        help="Preprocessing step, repeatable, applied in order, e.g. -s clip -s bin:2 "
        "-s calibrate:dark=dark.npy,white=white.npy. See `spektrify steps`.",
    ),
]
AsJson = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


def _load(
    path: Path,
    dataset: str | None,
    layout: Layout,
    mosaic: int | None,
    demosaic: str,
    steps: list[str] | None,
) -> Cube:
    from spektrify.io import load_cube
    from spektrify.preprocess import Pipeline

    try:
        pipeline = Pipeline.parse(steps or [])
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--step") from e
    try:
        cube = load_cube(
            path, dataset=dataset, layout=layout.value, mosaic=mosaic, demosaic_method=demosaic
        )
        return pipeline.apply(cube)
    except (OSError, ValueError, KeyError, ImportError) as e:
        raise typer.BadParameter(str(e), param_hint="CUBE") from e


def _print_json(obj: Any) -> None:
    from spektrify._json import dumps

    typer.echo(dumps(obj, indent=2))


def _version(value: bool) -> None:
    if value:
        from spektrify import __version__

        typer.echo(f"spektrify {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    """Multi/hyperspectral cube viewer and quick-look tools."""


@app.command()
def view(
    path: OptionalCubePath = None,
    demo: Annotated[
        bool, typer.Option(help="Open a synthetic cube with planted artefacts.")
    ] = False,
    dataset: Dataset = None,
    layout: LayoutOpt = Layout.auto,
    mosaic: Mosaic = None,
    demosaic: Demosaic = "block",
    step: Steps = None,
    port: Annotated[int, typer.Option(help="Port to listen on (0 = any free port).")] = 8765,
    host: Annotated[
        str, typer.Option(help="Bind address. On a remote box keep it and use ssh -L.")
    ] = "127.0.0.1",
    browser: Annotated[bool, typer.Option(help="Open a browser tab.")] = True,
) -> None:
    """Open the viewer in your browser (with no file, use the open dialog or drag & drop)."""
    from spektrify import serve
    from spektrify.io import demo_cube
    from spektrify.preprocess import Pipeline

    cube = None
    if demo:
        cube = Pipeline.parse(step or []).apply(demo_cube())
    elif path:
        cube = _load(path, dataset, layout, mosaic, demosaic, step)
    serve(cube, port=port, host=host, open_browser=browser)


class DemoName(str, Enum):
    scene = "scene"
    capture = "capture"
    photo = "photo"


@app.command()
def learn(
    path: OptionalCubePath = None,
    demo: Annotated[
        DemoName,
        typer.Option(
            help="Built-in cube when no file is given: scene, capture (raw counts) or photo (RGB)."
        ),
    ] = DemoName.scene,
    lessons: Annotated[
        list[Path] | None,
        typer.Option("--lessons", "-l", help="Folder (or file) of extra lessons, repeatable."),
    ] = None,
    check: Annotated[
        bool, typer.Option("--check", help="Only validate the lesson files and exit.")
    ] = False,
    dataset: Dataset = None,
    layout: LayoutOpt = Layout.auto,
    port: Annotated[int, typer.Option(help="Port to listen on (0 = any free port).")] = 8765,
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    browser: Annotated[bool, typer.Option(help="Open a browser tab.")] = True,
) -> None:
    """Learn spectral imaging step by step: interactive lessons on a demo cube or your own.

    Lessons are TOML files; write your own and load them with --lessons (see docs/learn.md).
    """
    from spektrify.learn import check_lessons, load_lessons

    dirs = lessons or []
    if check:
        errors = check_lessons(dirs)
        for e in errors:
            typer.echo(e, err=True)
        if errors:
            raise typer.Exit(1)
        typer.echo(f"{len(load_lessons(dirs))} lessons OK")
        return
    from spektrify import serve
    from spektrify.io import DEMOS

    try:
        load_lessons(dirs)  # fail here, not in the browser
    except (OSError, ValueError) as e:
        raise typer.BadParameter(str(e), param_hint="--lessons") from e
    cube = _load(path, dataset, layout, None, "block", None) if path else DEMOS[demo.value]()
    serve(cube, port=port, host=host, open_browser=browser, learn=True, lesson_dirs=dirs)


@app.command()
def info(
    path: CubePath,
    dataset: Dataset = None,
    layout: LayoutOpt = Layout.auto,
    mosaic: Mosaic = None,
    demosaic: Demosaic = "block",
    step: Steps = None,
    as_json: AsJson = False,
) -> None:
    """Print a cube's shape, spectral axis and value range."""
    from spektrify.compute import create_analyzer

    cube = _load(path, dataset, layout, mosaic, demosaic, step)
    an = create_analyzer(cube)
    g = an.global_range
    summary = {
        "name": cube.name,
        "height": cube.height,
        "width": cube.width,
        "bands": cube.n_bands,
        "axis": [float(cube.axis[0]), float(cube.axis[-1])],
        "unit": cube.axis_unit,
        "range": [g["min"], g["max"]],
        "p01_p99": [g["p01"], g["p99"]],
        "invalid_pixels": int((~an.finite_mask).sum()),
        "meta": cube.json_meta(),
    }
    if as_json:
        _print_json(summary)
        return
    from rich.console import Console
    from rich.table import Table

    t = Table(show_header=False, box=None, pad_edge=False)
    t.add_row("cube", f"{cube.name}  [dim]{cube.height} × {cube.width} × {cube.n_bands}[/]")
    unit = f" {cube.axis_unit}" if cube.axis_unit else ""
    t.add_row("axis", f"{cube.axis[0]:g} … {cube.axis[-1]:g}{unit}")
    t.add_row(
        "values",
        f"{g['min']:.5g} … {g['max']:.5g}  [dim](1–99%: {g['p01']:.4g} … {g['p99']:.4g})[/]",
    )
    t.add_row("invalid", f"{summary['invalid_pixels']:,} px with NaN / Inf")
    for k, v in summary["meta"].items():
        t.add_row(k, str(v))
    Console().print(t)


@app.command()
def quality(
    path: CubePath,
    dataset: Dataset = None,
    layout: LayoutOpt = Layout.auto,
    mosaic: Mosaic = None,
    demosaic: Demosaic = "block",
    step: Steps = None,
    as_json: AsJson = False,
    strict: Annotated[
        bool, typer.Option(help="Exit with code 1 if any issue is found (for scripts and CI).")
    ] = False,
) -> None:
    """Scan a cube for sensor artefacts: noisy, striped, saturated or invalid bands, bad lines."""
    from spektrify.compute import create_analyzer

    cube = _load(path, dataset, layout, mosaic, demosaic, step)
    q = create_analyzer(cube).quality
    if as_json:
        _print_json(q)
    else:
        from rich.console import Console
        from rich.table import Table

        con = Console()
        con.print(f"[bold]{cube.name}[/]  [dim]{cube.height} × {cube.width} × {cube.n_bands}[/]")
        for issue in q["issues"] or ["No problems detected."]:
            con.print(f"  {'[yellow]•[/]' if q['issues'] else '[green]✓[/]'} {issue}")
        if q["flags"]:
            t = Table("band", "λ", "reasons", box=None, header_style="dim")
            for f in q["flags"]:
                t.add_row(str(f["band"]), f"{cube.axis[f['band']]:g}", " · ".join(f["reasons"]))
            con.print(t)
    if strict and q["issues"]:
        raise typer.Exit(1)


@app.command()
def convert(
    path: CubePath,
    output: Annotated[
        Path, typer.Argument(help="Output .npz or .h5 (cube as H×W×C + wavelengths).")
    ],
    dataset: Dataset = None,
    layout: LayoutOpt = Layout.auto,
    mosaic: Mosaic = None,
    demosaic: Demosaic = "block",
    step: Steps = None,
) -> None:
    """Load (demosaic, preprocess) a cube and save it as .npz or .h5."""

    cube = _load(path, dataset, layout, mosaic, demosaic, step)
    _save(cube, output)


@app.command()
def demo(
    output: Annotated[Path, typer.Argument(help="Where to write it: .h5 or .npz.")] = Path(
        "demo.h5"
    ),
    raw: Annotated[
        bool,
        typer.Option(
            help="Write a raw 4×4 snapshot-mosaic frame in spektro's HDF5 layout instead, "
            "to try demosaicing."
        ),
    ] = False,
    size: Annotated[str, typer.Option(help="Image size as HxW.")] = "192x256",
    bands: Annotated[int, typer.Option(help="Number of bands (raw: always 16).")] = 96,
) -> None:
    """Write a synthetic cube with known objects and planted sensor artefacts to try things on.

    It has a leaf with a red edge, coated discs, a small anomaly, a dead column, a striped
    band, a noisy band, saturated pixels and a NaN patch.
    """
    from spektrify.io import demo_cube

    try:
        h, w = (int(v) for v in size.lower().split("x"))
    except ValueError:
        raise typer.BadParameter("use HxW, e.g. 192x256", param_hint="--size") from None
    if not raw:
        _save(demo_cube(h, w, bands), output)
        return
    from spektrify.io import mosaic, save_raw_mosaic

    if output.suffix.lower() not in (".h5", ".hdf5"):
        raise typer.BadParameter("raw mosaics are written as .h5", param_hint="OUTPUT")
    cube = demo_cube(h, w, 16)
    _require_h5py()
    save_raw_mosaic(mosaic(cube.data.transpose(1, 2, 0), 4), cube.axis, output)
    typer.echo(f"{output}  (raw {h * 4} × {w * 4} mosaic, 4×4 filters = 16 bands)")


def _require_h5py() -> None:
    try:
        import h5py  # noqa: F401
    except ImportError:
        raise typer.BadParameter(
            "writing .h5 needs h5py: pip install 'spektrify[hdf5]'", param_hint="OUTPUT"
        ) from None


def _save(cube: Cube, output: Path) -> None:
    from spektrify.io import save_cube
    from spektrify.io.writers import CUBE_SUFFIXES

    if output.suffix.lower() not in CUBE_SUFFIXES:
        raise typer.BadParameter(f"use one of {', '.join(CUBE_SUFFIXES)}", param_hint="OUTPUT")
    if output.suffix.lower() != ".npz":
        _require_h5py()
    save_cube(cube, output)
    typer.echo(f"{output}  ({cube.height} × {cube.width} × {cube.n_bands})")


@app.command()
def steps(as_json: AsJson = False) -> None:
    """List the preprocessing steps usable with --step and in the viewer."""
    from spektrify.preprocess import step_schema

    schema = step_schema()
    if as_json:
        _print_json(schema)
        return
    from rich.console import Console

    con = Console()
    for s in schema:
        con.print(f"[bold]{s['name']}[/]  {s['help']}")
        for p in s["params"]:
            con.print(f"    [cyan]{p['name']}[/]={p['default']!r}  [dim]{p['help']}[/]")


if __name__ == "__main__":
    app()
