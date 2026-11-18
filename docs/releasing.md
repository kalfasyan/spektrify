# Releasing

Versions follow [SemVer](https://semver.org/) and come from git tags: there is no version
number to edit in the code. Between releases, development builds get versions such as
`0.2.0.dev3+g1a2b3c4`.

1. Make sure `main` is green and `CHANGELOG.md` has the changes under **Unreleased**.
2. Move them under a new heading `## [X.Y.Z] - YYYY-MM-DD` and merge that.
3. Tag and push:

   ```bash
   git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0
   ```

The **Release** workflow then rebuilds the UI and checks it matches the committed bundle,
runs the tests, builds the wheel and sdist, checks that the version matches the tag, and
creates a GitHub release with generated notes and the files attached.

## Publishing to PyPI (one-time setup)

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API
token is stored anywhere.

1. On PyPI, add a pending trusted publisher for project `spektrify`: owner `kalfasyan`,
   repository `spektrify`, workflow `release.yml`, environment `pypi`.
2. In the GitHub repository settings, create an environment named `pypi` (optionally
   requiring your approval), and add the repository variable `PUBLISH_TO_PYPI` = `true`.

From then on every tag also publishes to PyPI.
