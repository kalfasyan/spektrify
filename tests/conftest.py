"""Shared fixtures: a small synthetic cube and a session serving it."""

from __future__ import annotations

import pytest

from spektrify.io import demo_cube
from spektrify.model import Cube
from spektrify.server.routes import Binary, Json, Request, dispatch
from spektrify.server.session import Session


@pytest.fixture(scope="module")
def demo() -> Cube:
    return demo_cube(height=48, width=64, bands=32, seed=1)


@pytest.fixture
def session(demo: Cube) -> Session:
    return Session(demo)


def _call(s: Session, name: str, method: str = "GET", body=None, **params) -> Json | Binary:
    req = Request(params={k: [str(v)] for k, v in params.items()}, body=body or {})
    return dispatch(s, method, name, req)


@pytest.fixture
def call():
    """Call an API route the way the HTTP adapter does: ``call(session, "band", i=3)``."""
    return _call
