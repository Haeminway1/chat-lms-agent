# User-owned after install: edit this private copy only; reinstall with --force to reset.
from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_SRC = Path(r"__REPO_SRC__")
PROFILE_ROOT = Path(r"__PROFILE_ROOT__")
sys.path.insert(0, str(REPO_SRC))

from chat_lms_agent.side_panel_lesson import lesson_panel_payload  # noqa: E402
from chat_lms_agent.state import ProfileState  # noqa: E402

VIEW_PATH = Path(__file__).with_name("lesson_panel_view.html")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        match parsed.path:
            case "/":
                self._write_html(VIEW_PATH.read_text(encoding="utf-8"))
            case "/api/health":
                self._write_json({"status": "PASS", "service": "lesson_panel"})
            case "/api/lesson-panel":
                self._write_json(self._lesson_payload(parsed.query))
            case _:
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()

    def log_message(self, _message_format: str, *_args: str) -> None:
        return

    def _lesson_payload(self, query: str) -> dict[str, object]:
        params = parse_qs(query)
        student = _first_param(params, "student") or "<student>"
        lesson_date = _first_param(params, "date")
        profile = ProfileState(root=PROFILE_ROOT.resolve(), repo_root=REPO_SRC.parent.resolve())
        return lesson_panel_payload(profile, student, lesson_date)

    def _write_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _first_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
