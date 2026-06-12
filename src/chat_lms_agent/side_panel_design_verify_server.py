from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Self, cast, override
from urllib import parse

if TYPE_CHECKING:
    from types import TracebackType

    from chat_lms_agent.state import JsonValue


class _FixtureHttpServer(ThreadingHTTPServer):
    artifact_html: str
    payload: dict[str, JsonValue]

    def __init__(
        self,
        server_address: tuple[str, int],
        artifact_html: str,
        payload: dict[str, JsonValue],
    ) -> None:
        super().__init__(server_address, _FixtureHandler)
        self.artifact_html = artifact_html
        self.payload = payload


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        server = cast("_FixtureHttpServer", self.server)
        parsed = parse.urlparse(self.path)
        if parsed.path in {"", "/", "/index.html"}:
            self._send_text(HTTPStatus.OK, "text/html; charset=utf-8", server.artifact_html)
            return
        if parsed.path.startswith("/api/"):
            body = json.dumps(server.payload, ensure_ascii=False, sort_keys=True)
            self._send_text(HTTPStatus.OK, "application/json; charset=utf-8", body)
            return
        self._send_text(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "not found")

    @override
    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_text(self, status: HTTPStatus, content_type: str, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        _ = self.wfile.write(encoded)


@dataclass(slots=True)
class _FixtureServer:
    artifact_html: str
    payload: dict[str, JsonValue]
    _server: _FixtureHttpServer | None = None
    _thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        server = _FixtureHttpServer(("127.0.0.1", 0), self.artifact_html, self.payload)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = exc_type
        _ = exc_value
        _ = traceback
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    @property
    def base_url(self) -> str:
        if self._server is None:
            return ""
        return f"http://127.0.0.1:{self._server.server_port}"

    def set_payload(self, payload: dict[str, JsonValue]) -> None:
        if self._server is not None:
            self._server.payload = payload


def fixture_server(artifact_html: str, payload: dict[str, JsonValue]) -> _FixtureServer:
    return _FixtureServer(artifact_html, payload)
