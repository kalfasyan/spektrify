"""``python -m spektrify`` / ``spektrify``: launch the spectral cube viewer."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="spektrify",
        description="Interactive multi/hyperspectral cube viewer (opens in your browser).",
    )
    p.add_argument("path", nargs="?", help="Cube file: .npy .npz .h5 .mat .hdr (ENVI) .tif")
    p.add_argument("--demo", action="store_true", help="Open a synthetic cube with artifacts.")
    p.add_argument("--dataset", help="Array name inside an HDF5 / NPZ / MAT container.")
    p.add_argument(
        "--layout",
        default="auto",
        choices=["auto", "hwc", "chw"],
        help="Axis order of the stored array (default: guess).",
    )
    p.add_argument("--mosaic", type=int, help="Demosaic a 2-D snapshot mosaic (macropixel size).")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. For remote boxes keep it and use `ssh -L 8765:localhost:8765`.",
    )
    p.add_argument("--no-browser", action="store_true", help="Don't open a browser tab.")
    a = p.parse_args(argv)

    from spektrify import serve

    serve(
        a.path,
        demo=a.demo,
        dataset=a.dataset,
        layout=a.layout,
        mosaic=a.mosaic,
        port=a.port,
        host=a.host,
        open_browser=not a.no_browser,
    )


if __name__ == "__main__":
    main()
