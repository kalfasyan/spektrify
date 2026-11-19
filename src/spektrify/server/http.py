"""Stdlib HTTP transport: serves the static frontend and adapts requests to :mod:`routes`.

Arrays travel as raw little-endian bytes with a JSON ``X-Meta`` header, so a band of a
1024² cube is a 4 MB memcpy on localhost. Swap this module for another transport without
touching routes, compute or the frontend.
"""

from __future__ import annotations

import contextlib
import json
import mimetypes
import os
import socket
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np

from spektrify._json import dumps
from spektrify.server.routes import ApiError, Binary, Json, Request, dispatch
from spektrify.server.session import Session

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_CLIENT_ERRORS = (
    ValueError,
    TypeError,
    NameError,
    SyntaxError,
    IndexError,
    KeyError,
    ZeroDivisionError,
)


def make_handler(session: Session) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "spektrify"
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (base-class name)
            if os.environ.get("SPEKTRIFY_DEBUG"):
                super().log_message(format, *args)

        def _send(
            self, status: int, body: bytes, ctype: str, headers: dict[str, str] | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _write(self, res: Json | Binary) -> None:
            if isinstance(res, Json):
                self._send(res.status, dumps(res.obj).encode(), "application/json")
                return
            arr = np.ascontiguousarray(res.array)
            if arr.dtype.byteorder == ">":
                arr = arr.astype(arr.dtype.newbyteorder("<"))
            meta = {**res.meta, "dtype": str(arr.dtype), "shape": list(arr.shape)}
            self._send(
                200,
                arr.tobytes(),
                "application/octet-stream",
                {"X-Meta": dumps(meta), "X-Generation": str(session.generation)},
            )

        def do_GET(self) -> None:
            self._handle("GET")

        def do_HEAD(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def _handle(self, method: str) -> None:
            url = urlparse(self.path)
            try:
                if not url.path.startswith("/api/"):
                    return self._static(url.path)
                length = int(self.headers.get("Content-Length") or 0)
                req = Request(params=parse_qs(url.query), length=length)
                name = url.path[5:].strip("/")
                if method == "POST" and name == "upload":
                    req.stream = self.rfile
                elif length:
                    req.body = json.loads(self.rfile.read(length) or b"{}")
                self._write(dispatch(session, method, name, req))
            except ApiError as e:
                self._write(Json({"error": str(e)}, e.status))
            except FileNotFoundError as e:
                self._write(Json({"error": f"File not found: {e}"}, 404))
            except LookupError as e:
                self._write(Json({"error": str(e)}, 404 if "No cube" in str(e) else 400))
            except _CLIENT_ERRORS as e:
                self._write(Json({"error": f"{type(e).__name__}: {e}"}, 400))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:  # pragma: no cover - surfaced in the UI
                traceback.print_exc()
                with contextlib.suppress(OSError):
                    self._write(Json({"error": f"{type(e).__name__}: {e}"}, 500))

        def _static(self, path: str) -> None:
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (STATIC_DIR / rel).resolve()
            if STATIC_DIR not in target.parents or not target.is_file():
                raise ApiError(404, "not found")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix == ".js":
                ctype = "text/javascript"
            self._send(200, target.read_bytes(), ctype)

    return Handler


def _free_port(host: str, preferred: int) -> int:
    for port in ([preferred] if preferred else []) + [0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise OSError("no free port")


class ViewerServer:
    """A viewer bound to ``host:port``; ``start()`` runs it in a background thread."""

    def __init__(self, session: Session, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.session = session
        self.host = host
        self.port = _free_port(host, port)
        self.httpd = ThreadingHTTPServer((host, self.port), make_handler(session))
        self.httpd.daemon_threads = True

    @property
    def url(self) -> str:
        host = "localhost" if self.host in ("127.0.0.1", "0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}/"

    def start(self) -> ViewerServer:
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def serve_forever(self, open_browser: bool = True, page: str = "") -> None:
        """Serve until Ctrl+C. ``page`` is appended to the URL opened in the browser."""
        if open_browser:
            threading.Timer(0.4, lambda: webbrowser.open(self.url + page)).start()
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.httpd.server_close()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
