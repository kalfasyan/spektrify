# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/): the version comes from the git tag (`vX.Y.Z`).

## [Unreleased]

First release (to be tagged `v0.1.0`).

### Added
- Browser-based viewer: band / RGB / PCA / anomaly / similarity / stats / band-math display,
  spectra and line profiles, all-channels grid, 3D slice cube, volume rendering and PCA
  cloud, and a data-quality dashboard.
- Readers for .npy / .npz, HDF5, MATLAB, TIFF and ENVI, including spektro's raw mosaic HDF5
  files (the macropixel size is inferred from the number of filters).
- Demosaicing methods for snapshot-mosaic sensors: `block` (as in spektro) and `bilinear`
  (full sensor resolution, channels co-registered).
- Preprocessing pipeline with registered, composable steps: `clip` (spektro's per-band
  percentile clipper), `calibrate` (dark / white reference), `crop`, `bands`, `bin`. Usable
  from Python (`Pipeline`), the CLI (`--step`) and the viewer's Preprocess panel.
- Command line built with Typer: `spektrify view | info | quality | convert | steps`, with
  `--json` output and `quality --strict` (exit code 1 on issues) for scripts and CI.
- Python API: `show()` / `Viewer.update()` for notebooks, `serve()`, `load_cube()`.
- uv project with a lock file, ruff, ty type checking, pytest with coverage. CI on Linux,
  macOS and Windows (Python 3.10–3.13), a wheel smoke test, and a tag-driven release workflow
  (GitHub release, optional PyPI trusted publishing).

[Unreleased]: https://github.com/kalfasyan/spektrify/commits/main
