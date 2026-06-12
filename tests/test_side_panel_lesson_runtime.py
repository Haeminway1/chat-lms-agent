from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def test_lesson_install_assets_creates_substituted_user_owned_templates(
    tmp_path: Path,
) -> None:
    # Given: an empty private profile.
    profile_root = tmp_path / "profile"

    # When: lesson assets are installed.
    result = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: both user-owned templates exist with placeholders replaced.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["created"] == ["lesson_panel_server.py", "lesson_panel_view.html"]
    scripts = profile_root / "codex-workspace" / "scripts"
    server = scripts / "lesson_panel_server.py"
    view = scripts / "lesson_panel_view.html"
    assert "user-owned after install" in server.read_text(encoding="utf-8").lower()
    assert "user-owned after install" in view.read_text(encoding="utf-8").lower()
    assert "__REPO_SRC__" not in server.read_text(encoding="utf-8")
    assert "__PROFILE_ROOT__" not in server.read_text(encoding="utf-8")
    assert "__REPO_SRC__" not in view.read_text(encoding="utf-8")
    assert "__PROFILE_ROOT__" not in view.read_text(encoding="utf-8")
    assert str(profile_root) not in result.stdout
    lint = _run_cli(
        "side-panel",
        "design",
        "lint",
        "--artifact",
        str(view),
        "--mode",
        "all",
        "--json",
    )
    assert lint.returncode == 0, lint.stdout
    lint_payload = json.loads(lint.stdout)
    assert lint_payload["checked_modes"] == ["panel", "fullscreen"]


def test_lesson_install_assets_is_idempotent_and_force_overwrites(tmp_path: Path) -> None:
    # Given: lesson assets have already been installed and then user-edited.
    profile_root = tmp_path / "profile"
    first = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    assert first.returncode == 0, first.stderr
    server = profile_root / "codex-workspace" / "scripts" / "lesson_panel_server.py"
    server.write_text("# user edit\n", encoding="utf-8")

    # When: install-assets runs without force.
    second = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: the user edit is preserved and reported as skipped.
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["status"] == "SKIPPED"
    assert server.read_text(encoding="utf-8") == "# user edit\n"

    # When: install-assets runs with --force.
    forced = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--force",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: the template is overwritten.
    assert forced.returncode == 0, forced.stderr
    assert json.loads(forced.stdout)["status"] == "PASS"
    assert "user-owned after install" in server.read_text(encoding="utf-8").lower()


def test_lesson_server_e2e_serves_health_and_typed_payload(tmp_path: Path) -> None:
    # Given: installed lesson panel assets and a free ephemeral port.
    profile_root = tmp_path / "profile"
    install = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    assert install.returncode == 0, install.stderr
    port = _unused_tcp_port()
    server_path = profile_root / "codex-workspace" / "scripts" / "lesson_panel_server.py"

    process = subprocess.Popen(
        [sys.executable, str(server_path), "--port", str(port)],
        cwd=server_path.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # When: the installed stdlib server starts.
        health = _poll_json(port, "/api/health")
        api_path = (
            "/api/lesson-panel?student=%EA%B0%80%EC%83%81%ED%95%99%EC%83%9D"
            "&date=2026-06-12"
        )
        payload = _http_json(port, api_path)
    finally:
        _stop_process(process)

    # Then: both the healthcheck and typed JSON API are available.
    assert health["service"] == "lesson_panel"
    assert payload["view_id"] == "lesson_prep"
    assert payload["entity_ref"] == "learner:가상학생"
    assert payload["source_commands"]
    assert payload["sections"]


def test_lesson_ensure_server_and_open_plan_use_runtime(tmp_path: Path) -> None:
    # Given: installed lesson assets and an unused port.
    profile_root = tmp_path / "profile"
    install = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    assert install.returncode == 0, install.stderr
    port = _unused_tcp_port()

    # When: the agent checks startability, starts the server, and asks for the browser URL.
    dry_run = _run_cli(
        "side-panel",
        "lesson",
        "ensure-server",
        "--dry-run",
        "--port",
        str(port),
        "--profile-root",
        str(profile_root),
        "--json",
    )
    real_start = _run_cli(
        "side-panel",
        "lesson",
        "ensure-server",
        "--port",
        str(port),
        "--profile-root",
        str(profile_root),
        "--json",
    )
    try:
        open_plan = _run_cli(
            "side-panel",
            "lesson",
            "open-plan",
            "--student",
            "가상학생",
            "--date",
            "2026-06-12",
            "--port",
            str(port),
            "--profile-root",
            str(profile_root),
            "--json",
        )
        payload = _http_json(
            port,
            "/api/lesson-panel?student=%EA%B0%80%EC%83%81%ED%95%99%EC%83%9D",
        )
    finally:
        pid = _payload_pid(real_start.stdout)
        if pid is not None:
            _terminate_pid(pid)

    # Then: the runtime reports startable/running and the browser URL reaches typed JSON.
    assert dry_run.returncode == 0, dry_run.stderr
    assert json.loads(dry_run.stdout)["status"] == "WOULD_START"
    assert real_start.returncode == 0, real_start.stderr
    assert json.loads(real_start.stdout)["status"] == "PASS"
    assert open_plan.returncode == 0, open_plan.stderr
    browser_url = json.loads(open_plan.stdout)["browser_url"]
    assert browser_url == f"http://127.0.0.1:{port}/?student=%EA%B0%80%EC%83%81%ED%95%99%EC%83%9D&date=2026-06-12"
    assert payload["view_id"] == "lesson_prep"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root,
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )


def _http_json(port: int, path: str) -> dict[str, JsonValue]:
    connection = HTTPConnection("127.0.0.1", port, timeout=2.0)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert isinstance(payload, dict)
        return payload
    finally:
        connection.close()


def _poll_json(port: int, path: str) -> dict[str, JsonValue]:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            return _http_json(port, path)
        except (AssertionError, ConnectionError, OSError):
            time.sleep(0.1)
    message = "server did not become ready"
    raise AssertionError(message)


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _ = process.communicate(timeout=5)


def _payload_pid(raw_stdout: str) -> int | None:
    payload = json.loads(raw_stdout)
    pid = payload.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool):
        return pid
    return None


def _terminate_pid(pid: int) -> None:
    if sys.platform == "win32":
        command = ["taskkill", "/PID", str(pid), "/T", "/F"]
    else:
        command = ["kill", str(pid)]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _ = process.communicate(timeout=5)
