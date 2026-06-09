from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

import chat_lms_agent.side_panel_wordbook as wordbook_runtime
from chat_lms_agent.side_panel_wordbook import _probe_from_transport_error
from chat_lms_agent.state import ProfileState

if TYPE_CHECKING:
    import pytest


def test_wordbook_open_plan_returns_browser_url_for_synthetic_profile(
    tmp_path: Path,
) -> None:
    # Given: a private profile contains the user-owned lesson wordbook runtime.
    _write_wordbook_runtime(tmp_path)
    port = _unused_tcp_port()

    # When: the side-panel harness plans a learner wordbook panel open.
    result = _run_cli(
        "side-panel",
        "wordbook",
        "open-plan",
        "--student",
        "Synthetic Learner",
        "--date",
        "2026-06-10",
        "--port",
        str(port),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the agent receives a browser URL and next CLI action without searching files.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["browser_url"] == (
        f"http://127.0.0.1:{port}/?student=Synthetic+Learner&date=2026-06-10"
    )
    assert payload["server"]["status"] == "not_running"
    assert payload["next_action"] == "use_default_wordbook_port_or_connect_running_runtime"
    assert payload["supported_runtime_port"] == 8765
    assert "side-panel wordbook ensure-server" in payload["ensure_server_command"]
    assert str(tmp_path) not in result.stdout


def test_wordbook_ensure_server_reports_unsupported_custom_port(tmp_path: Path) -> None:
    # Given: the user-owned runtime assets exist, but the requested port is not supported.
    _write_wordbook_runtime(tmp_path)
    port = _unused_tcp_port()

    # When: the agent asks the harness to ensure the custom port.
    result = _run_cli(
        "side-panel",
        "wordbook",
        "ensure-server",
        "--port",
        str(port),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the harness blocks with an explicit reason instead of starting the default port.
    assert result.returncode == 5
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "WORDBOOK_PORT_UNSUPPORTED"
    assert payload["supported_runtime_port"] == 8765
    assert payload["server"]["port"] == port
    assert "pid" not in payload


def test_wordbook_open_plan_reports_wrong_server_on_panel_port(
    tmp_path: Path,
) -> None:
    # Given: another local service occupies the requested wordbook port.
    _write_wordbook_runtime(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StaticOnlyHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # When: planning a wordbook open against that occupied port.
        result = _run_cli(
            "side-panel",
            "wordbook",
            "open-plan",
            "--student",
            "Synthetic Learner",
            "--port",
            str(port),
            "--profile-root",
            str(tmp_path),
            "--json",
        )
    finally:
        server.shutdown()
        server.server_close()

    # Then: the harness reports the conflict instead of pretending the panel works.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["server"]["status"] == "wrong_service"
    assert payload["next_action"] == "resolve_port_conflict"
    assert payload["server"]["healthcheck"] == f"http://127.0.0.1:{port}/api/lookup"


def test_wordbook_timeout_probe_reports_unresponsive_service() -> None:
    probe = _probe_from_transport_error("http://127.0.0.1:8765/api/lookup", "timeout")

    assert probe.status == "unresponsive"


def test_wordbook_ensure_server_blocks_unresponsive_panel_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a local service accepts the wordbook port but never returns a response.
    _write_wordbook_runtime(tmp_path)
    monkeypatch.setattr(wordbook_runtime, "SERVER_HEALTHCHECK_TIMEOUT_SECONDS", 0.05)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StalledHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # When: the harness is asked to ensure that port.
        code, payload = wordbook_runtime.ensure_wordbook_server(
            _profile_state(tmp_path),
            port,
            dry_run=False,
        )
    finally:
        server.shutdown()
        server.server_close()

    # Then: the occupied port is blocked instead of launching another runtime.
    assert code == 5
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "WORDBOOK_PORT_UNRESPONSIVE"
    assert payload["server"]["status"] == "unresponsive"
    assert payload["server"]["port"] == port
    assert "pid" not in payload


def test_context_hydrate_includes_wordbook_side_panel_route(tmp_path: Path) -> None:
    # Given: a new session hydrates the side-panel inventory.
    result = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-codex",
        "--json",
    )

    # Then: learner wordbook panel requests are routed to the CLI before file search.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    route = payload["side_panel"]["runtime_routes"]["lesson_wordbook"]
    request_text = "가상학생 단어 html 패널 열어줘"
    assert any(trigger.lower() in request_text.lower() for trigger in route["triggers"])
    assert route["first_command"].startswith("side-panel wordbook open-plan")
    assert route["browser_action"] == "open browser_url with Browser plugin"
    assert route["file_search_policy"] == "do_not_rg_before_cli_route"


class _StaticOnlyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def log_message(self, _message_format: str, *_args: str) -> None:
        return


class _StalledHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        time.sleep(1.0)

    def log_message(self, _message_format: str, *_args: str) -> None:
        return


def _write_wordbook_runtime(profile_root: Path) -> None:
    scripts = profile_root / "codex-workspace" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "lesson_wordbook_server.py").write_text("print('synthetic')\n", encoding="utf-8")
    (scripts / "lesson_wordbook_view.html").write_text("<html></html>\n", encoding="utf-8")


def _profile_state(profile_root: Path) -> ProfileState:
    return ProfileState(root=profile_root.resolve(), repo_root=Path(__file__).resolve().parents[1])


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
