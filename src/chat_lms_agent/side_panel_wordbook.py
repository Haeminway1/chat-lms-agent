from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, assert_never, cast
from urllib.parse import urlencode

from chat_lms_agent.hosts import active_host
from chat_lms_agent.side_panel_runtime import (
    ServerProbe,
    next_action_for_probe,
    probe_from_transport_error,
    read_local_http,
    server_probe_json,
    start_local_server,
    wait_for_server,
)

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

DEFAULT_WORDBOOK_PORT: Final = 8765
SERVER_CHECK_WORD: Final = "probe"
SERVER_HEALTHCHECK_TIMEOUT_SECONDS: Final = 6.0
SERVER_START_WAIT_SECONDS: Final = 12.0
SERVER_START_POLL_SECONDS: Final = 0.2

ServerStatus = Literal["running", "not_running", "wrong_service", "unresponsive"]


@dataclass(frozen=True, slots=True)
class WordbookAssets:
    server_path: str
    view_path: str


def wordbook_open_plan(
    profile: ProfileState,
    student: str,
    lesson_date: str | None,
    port: int,
) -> tuple[int, dict[str, JsonValue]]:
    assets = _wordbook_assets(profile)
    if assets is None:
        return 4, _missing_assets_payload()
    probe = _probe_wordbook_server(port)
    return (
        0,
        {
            "status": "PASS",
            "kind": "lesson_wordbook",
            "student": student,
            "browser_url": _wordbook_url(student, lesson_date, port),
            "server": _server_probe_json(probe),
            "supported_runtime_port": DEFAULT_WORDBOOK_PORT,
            "runtime_assets": _runtime_assets_json(),
            "ensure_server_command": (
                "side-panel wordbook ensure-server --profile-root <profile-root> --json"
            ),
            "browser_action": "open browser_url with Browser plugin",
            "file_search_policy": "do_not_rg_before_cli_route",
            "next_action": _next_action(probe.status, port),
        },
    )


def ensure_wordbook_server(
    profile: ProfileState,
    port: int,
    *,
    dry_run: bool,
) -> tuple[int, dict[str, JsonValue]]:
    assets = _wordbook_assets(profile)
    if assets is None:
        return 4, _missing_assets_payload()
    probe = _probe_wordbook_server(port)
    match probe.status:
        case "running":
            return 0, _ensure_payload("PASS", probe, pid=None)
        case "wrong_service" | "unresponsive":
            return 5, _ensure_payload("BLOCKED", probe, pid=None)
        case "not_running":
            if port != DEFAULT_WORDBOOK_PORT:
                return 5, _unsupported_port_payload(probe)
            if dry_run:
                return 0, _ensure_payload("WOULD_START", probe, pid=None)
            pid = _start_wordbook_server(profile, assets)
            started_probe = _wait_for_wordbook_server(port)
            status = "PASS" if started_probe.status == "running" else "BLOCKED"
            code = 0 if started_probe.status == "running" else 5
            return code, _ensure_payload(status, started_probe, pid=pid)
    assert_never(probe.status)


def _wordbook_assets(profile: ProfileState) -> WordbookAssets | None:
    scripts_dir = profile.root / active_host().workspace_dirname / "scripts"
    server_path = scripts_dir / "lesson_wordbook_server.py"
    view_path = scripts_dir / "lesson_wordbook_view.html"
    if not server_path.exists() or not view_path.exists():
        return None
    return WordbookAssets(server_path=str(server_path), view_path=str(view_path))


def _wordbook_url(student: str, lesson_date: str | None, port: int) -> str:
    params = {"student": student}
    if lesson_date is not None:
        params["date"] = lesson_date
    return f"http://127.0.0.1:{port}/?{urlencode(params)}"


def _probe_wordbook_server(port: int) -> ServerProbe:
    healthcheck = f"http://127.0.0.1:{port}/api/lookup"
    query = urlencode({"words": SERVER_CHECK_WORD})
    path = f"/api/lookup?{query}"
    status, body = _read_local_http(port, path)
    return _probe_from_response(healthcheck, status, body)


def _read_local_http(port: int, path: str) -> tuple[int | None, str]:
    return read_local_http(port, path, timeout_seconds=SERVER_HEALTHCHECK_TIMEOUT_SECONDS)


def _probe_from_response(healthcheck: str, status: int | None, body: str) -> ServerProbe:
    if status is None:
        return _probe_from_transport_error(healthcheck, body)
    if status != HTTPStatus.OK:
        return ServerProbe(
            status="wrong_service",
            healthcheck=healthcheck,
            detail=f"http_{status}",
        )
    try:
        payload = cast("JsonValue", json.loads(body))
    except JSONDecodeError:
        return ServerProbe(status="wrong_service", healthcheck=healthcheck, detail="invalid_json")
    if isinstance(payload, dict) and isinstance(payload.get("words"), list):
        return ServerProbe(status="running", healthcheck=healthcheck, detail="lesson_wordbook_api")
    return ServerProbe(status="wrong_service", healthcheck=healthcheck, detail="unexpected_payload")


def _probe_from_transport_error(healthcheck: str, detail: str) -> ServerProbe:
    return probe_from_transport_error(healthcheck, detail)


def _wait_for_wordbook_server(port: int) -> ServerProbe:
    return wait_for_server(
        port,
        _probe_wordbook_server,
        wait_seconds=SERVER_START_WAIT_SECONDS,
        poll_seconds=SERVER_START_POLL_SECONDS,
    )


def _start_wordbook_server(profile: ProfileState, assets: WordbookAssets) -> int:
    script_dir = profile.root / active_host().workspace_dirname / "scripts"
    return start_local_server(assets.server_path, script_dir, ())


def _ensure_payload(status: str, probe: ServerProbe, pid: int | None) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "status": status,
        "kind": "lesson_wordbook",
        "server": _server_probe_json(probe),
    }
    if pid is not None:
        payload["pid"] = pid
    if probe.status == "wrong_service":
        payload["error_code"] = "WORDBOOK_PORT_OCCUPIED_BY_WRONG_SERVICE"
        payload["next_action"] = "stop_conflicting_service_or_choose_a_supported_port"
    if probe.status == "unresponsive":
        payload["error_code"] = "WORDBOOK_PORT_UNRESPONSIVE"
        payload["next_action"] = "stop_or_inspect_local_service_on_port"
    return payload


def _unsupported_port_payload(probe: ServerProbe) -> dict[str, JsonValue]:
    return {
        "status": "BLOCKED",
        "error_code": "WORDBOOK_PORT_UNSUPPORTED",
        "message": "lesson wordbook runtime currently starts on port 8765",
        "supported_runtime_port": DEFAULT_WORDBOOK_PORT,
        "server": _server_probe_json(probe),
    }


def _missing_assets_payload() -> dict[str, JsonValue]:
    return {
        "status": "BLOCKED",
        "error_code": "WORDBOOK_RUNTIME_MISSING",
        "message": "private profile does not contain lesson wordbook runtime assets",
        "runtime_assets": _runtime_assets_json(),
    }


def _server_probe_json(probe: ServerProbe) -> dict[str, JsonValue]:
    return server_probe_json(probe, default_port=DEFAULT_WORDBOOK_PORT)


def _runtime_assets_json() -> dict[str, JsonValue]:
    scripts = f"<profile-root>/{active_host().workspace_dirname}/scripts"
    return {
        "server": f"{scripts}/lesson_wordbook_server.py",
        "view": f"{scripts}/lesson_wordbook_view.html",
    }


def _next_action(status: ServerStatus, port: int) -> str:
    match status:
        case "running":
            return "open_browser_url"
        case "not_running":
            if port != DEFAULT_WORDBOOK_PORT:
                return "use_default_wordbook_port_or_connect_running_runtime"
            return "run_ensure_server_then_open_browser_url"
        case "wrong_service":
            return "resolve_port_conflict"
        case "unresponsive":
            return next_action_for_probe(
                status,
                running="open_browser_url",
                not_running="run_ensure_server_then_open_browser_url",
                wrong_service="resolve_port_conflict",
                unresponsive="inspect_wordbook_server",
            )
    assert_never(status)
