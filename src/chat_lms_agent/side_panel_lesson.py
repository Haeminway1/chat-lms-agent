from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast
from urllib.parse import urlencode

from chat_lms_agent.hosts import active_host
from chat_lms_agent.side_panel_lesson_payload import LESSON_VIEW_ID, lesson_panel_payload
from chat_lms_agent.side_panel_runtime import (
    ServerProbe,
    ServerStatus,
    next_action_for_probe,
    probe_from_transport_error,
    read_local_http,
    server_probe_json,
    start_local_server,
    wait_for_server,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

DEFAULT_LESSON_PORT: Final = 8766
__all__ = ("lesson_panel_payload",)


@dataclass(frozen=True, slots=True)
class LessonAssets:
    server_path: str
    view_path: str


def lesson_open_plan(
    profile: ProfileState,
    student: str,
    lesson_date: str | None,
    view: str,
    port: int,
) -> tuple[int, dict[str, JsonValue]]:
    assets = _lesson_assets(profile)
    if assets is None:
        return 4, _missing_assets_payload(student, lesson_date, view, port)
    probe = _probe_lesson_server(port)
    return 0, {
        "status": "PASS",
        "kind": "lesson_assistant_panel",
        "student": student,
        "view": view,
        "browser_url": _lesson_url(student, lesson_date, port),
        "server": _server_probe_json(probe),
        "supported_runtime_port": DEFAULT_LESSON_PORT,
        "runtime_assets": _runtime_assets_json(),
        "ensure_server_command": (
            "side-panel lesson ensure-server --profile-root <profile-root> --json"
        ),
        "browser_action": "open browser_url with Browser plugin",
        "file_search_policy": "do_not_rg_before_cli_route",
        "next_action": _next_action(probe.status),
    }


def records_open_plan(
    profile: ProfileState,
    student: str,
    record_type: str,
    recent: int | None,
    port: int,
) -> tuple[int, dict[str, JsonValue]]:
    assets = _lesson_assets(profile)
    if assets is None:
        return 4, _missing_assets_payload(student, None, LESSON_VIEW_ID, port)
    probe = _probe_lesson_server(port)
    return 0, {
        "status": "PASS",
        "kind": "learner_records",
        "student": student,
        "record_type": record_type,
        "browser_url": _records_url(student, record_type, recent, port),
        "server": _server_probe_json(probe),
        "supported_runtime_port": DEFAULT_LESSON_PORT,
        "runtime_assets": _runtime_assets_json(),
        "ensure_server_command": (
            "side-panel lesson ensure-server --profile-root <profile-root> --json"
        ),
        "browser_action": "open browser_url with Browser plugin",
        "file_search_policy": "do_not_rg_before_cli_route",
        "next_action": _next_action(probe.status),
    }


def _records_url(student: str, record_type: str, recent: int | None, port: int) -> str:
    params = {"view": "records", "type": record_type, "student": student}
    if recent is not None:
        params["recent"] = str(recent)
    return f"http://127.0.0.1:{port}/?{urlencode(params)}"


def ensure_lesson_server(
    profile: ProfileState,
    port: int,
    *,
    dry_run: bool,
) -> tuple[int, dict[str, JsonValue]]:
    assets = _lesson_assets(profile)
    if assets is None:
        return 4, _missing_assets_payload("<student>", None, LESSON_VIEW_ID, port)
    probe = _probe_lesson_server(port)
    match probe.status:
        case "running":
            return 0, _ensure_payload("PASS", probe, pid=None)
        case "wrong_service" | "unresponsive":
            return 5, _ensure_payload("BLOCKED", probe, pid=None)
        case "not_running":
            if dry_run:
                return 0, _ensure_payload("WOULD_START", probe, pid=None)
            pid = _start_lesson_server(profile, assets, port)
            started_probe = _wait_for_lesson_server(port)
            status = "PASS" if started_probe.status == "running" else "BLOCKED"
            code = 0 if started_probe.status == "running" else 5
            return code, _ensure_payload(status, started_probe, pid=pid)


def install_lesson_assets(
    profile: ProfileState,
    *,
    force: bool,
) -> tuple[int, dict[str, JsonValue]]:
    scripts_dir = profile.root / active_host().workspace_dirname / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    installed = _install_template_files(profile, scripts_dir, force=force)
    status = "SKIPPED" if not installed["created"] and not installed["overwritten"] else "PASS"
    payload: dict[str, JsonValue] = {
        "status": status,
        "kind": "lesson_assistant_panel",
        "force": force,
        "created": installed["created"],
        "skipped": installed["skipped"],
        "overwritten": installed["overwritten"],
        "runtime_assets_present": _lesson_assets(profile) is not None,
        "runtime_assets": _runtime_assets_json(),
    }
    return 0, payload


def _lesson_assets(profile: ProfileState) -> LessonAssets | None:
    scripts_dir = profile.root / active_host().workspace_dirname / "scripts"
    server_path = scripts_dir / "lesson_panel_server.py"
    view_path = scripts_dir / "lesson_panel_view.html"
    if not server_path.exists() or not view_path.exists():
        return None
    return LessonAssets(server_path=str(server_path), view_path=str(view_path))


def _install_template_files(
    profile: ProfileState,
    scripts_dir: Path,
    *,
    force: bool,
) -> dict[str, list[JsonValue]]:
    result: dict[str, list[JsonValue]] = {"created": [], "skipped": [], "overwritten": []}
    for name in ("lesson_panel_server.py", "lesson_panel_view.html"):
        source = profile.repo_root / "assets" / "side-panel" / name
        target = scripts_dir / name
        if target.exists() and not force:
            result["skipped"].append(name)
            continue
        existed = target.exists()
        text = source.read_text(encoding="utf-8")
        text = text.replace("__REPO_SRC__", str(profile.repo_root / "src"))
        text = text.replace("__PROFILE_ROOT__", str(profile.root))
        _ = target.write_text(text, encoding="utf-8")
        result["overwritten" if existed else "created"].append(name)
    return result


def _missing_assets_payload(
    student: str,
    lesson_date: str | None,
    view: str,
    port: int,
) -> dict[str, JsonValue]:
    payload = _base_payload(student, lesson_date, view, port)
    payload["status"] = "BLOCKED"
    payload["error_code"] = "LESSON_RUNTIME_MISSING"
    payload["message"] = "private profile does not contain lesson panel runtime assets"
    payload["next_action"] = (
        "side-panel lesson install-assets --profile-root <profile-root> --json"
    )
    return payload


def _base_payload(
    student: str,
    lesson_date: str | None,
    view: str,
    port: int,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "kind": "lesson_assistant_panel",
        "student": student,
        "view": view,
        "supported_runtime_port": DEFAULT_LESSON_PORT,
        "requested_port": port,
        "runtime_assets": _runtime_assets_json(),
    }
    if lesson_date is not None:
        payload["date"] = lesson_date
    return payload


def _runtime_assets_json() -> dict[str, JsonValue]:
    scripts = f"<profile-root>/{active_host().workspace_dirname}/scripts"
    return {
        "server": f"{scripts}/lesson_panel_server.py",
        "view": f"{scripts}/lesson_panel_view.html",
    }


def _lesson_url(student: str, lesson_date: str | None, port: int) -> str:
    params = {"student": student}
    if lesson_date is not None:
        params["date"] = lesson_date
    return f"http://127.0.0.1:{port}/?{urlencode(params)}"


def _probe_lesson_server(port: int) -> ServerProbe:
    healthcheck = f"http://127.0.0.1:{port}/api/health"
    status, body = read_local_http(
        port,
        "/api/health",
        timeout_seconds=6.0,
    )
    if status is None:
        return probe_from_transport_error(healthcheck, body)
    if status != HTTPStatus.OK:
        return ServerProbe(status="wrong_service", healthcheck=healthcheck, detail=f"http_{status}")
    try:
        payload = cast("JsonValue", json.loads(body))
    except JSONDecodeError:
        return ServerProbe(status="wrong_service", healthcheck=healthcheck, detail="invalid_json")
    if isinstance(payload, dict) and payload.get("service") == "lesson_panel":
        return ServerProbe(status="running", healthcheck=healthcheck, detail="lesson_panel_api")
    return ServerProbe(status="wrong_service", healthcheck=healthcheck, detail="unexpected_payload")


def _wait_for_lesson_server(port: int) -> ServerProbe:
    return wait_for_server(port, _probe_lesson_server)


def _start_lesson_server(profile: ProfileState, assets: LessonAssets, port: int) -> int:
    script_dir = profile.root / active_host().workspace_dirname / "scripts"
    return start_local_server(assets.server_path, script_dir, ("--port", str(port)))


def _ensure_payload(status: str, probe: ServerProbe, pid: int | None) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "status": status,
        "kind": "lesson_assistant_panel",
        "server": _server_probe_json(probe),
    }
    if pid is not None:
        payload["pid"] = pid
    if probe.status == "wrong_service":
        payload["error_code"] = "LESSON_PORT_OCCUPIED_BY_WRONG_SERVICE"
        payload["next_action"] = "stop_conflicting_service_or_choose_another_port"
    if probe.status == "unresponsive":
        payload["error_code"] = "LESSON_PORT_UNRESPONSIVE"
        payload["next_action"] = "stop_or_inspect_local_service_on_port"
    return payload


def _server_probe_json(probe: ServerProbe) -> dict[str, JsonValue]:
    return server_probe_json(probe, default_port=DEFAULT_LESSON_PORT)


def _next_action(status: ServerStatus) -> str:
    return next_action_for_probe(
        status,
        running="open_browser_url",
        not_running="run_ensure_server_then_open_browser_url",
        wrong_service="resolve_port_conflict",
        unresponsive="inspect_lesson_server",
    )
