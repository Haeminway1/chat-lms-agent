from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from chat_lms_agent.hosts import active_host

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

DEFAULT_LESSON_PORT: Final = 8766


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
    return 5, _runtime_pending_payload(student, lesson_date, view, port)


def ensure_lesson_server(
    profile: ProfileState,
    port: int,
    *,
    dry_run: bool,
) -> tuple[int, dict[str, JsonValue]]:
    assets = _lesson_assets(profile)
    if assets is None:
        return 4, _missing_assets_payload("<student>", None, "lesson_prep", port)
    status = "WOULD_START" if dry_run else "BLOCKED"
    payload = _runtime_pending_payload("<student>", None, "lesson_prep", port)
    payload["status"] = status
    return (0 if dry_run else 5), payload


def install_lesson_assets(
    profile: ProfileState,
    *,
    force: bool,
) -> tuple[int, dict[str, JsonValue]]:
    assets = _lesson_assets(profile)
    payload: dict[str, JsonValue] = {
        "status": "BLOCKED",
        "kind": "lesson_assistant_panel",
        "error_code": "LESSON_INSTALL_ASSETS_NOT_IMPLEMENTED",
        "message": "lesson panel install-assets is implemented in Wave 3",
        "force": force,
        "runtime_assets_present": assets is not None,
        "runtime_assets": _runtime_assets_json(),
    }
    return 5, payload


def _lesson_assets(profile: ProfileState) -> LessonAssets | None:
    scripts_dir = profile.root / active_host().workspace_dirname / "scripts"
    server_path = scripts_dir / "lesson_panel_server.py"
    view_path = scripts_dir / "lesson_panel_view.html"
    if not server_path.exists() or not view_path.exists():
        return None
    return LessonAssets(server_path=str(server_path), view_path=str(view_path))


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


def _runtime_pending_payload(
    student: str,
    lesson_date: str | None,
    view: str,
    port: int,
) -> dict[str, JsonValue]:
    payload = _base_payload(student, lesson_date, view, port)
    payload["status"] = "BLOCKED"
    payload["error_code"] = "LESSON_RUNTIME_PENDING_WAVE3"
    payload["message"] = "lesson panel server startup is implemented in Wave 3"
    payload["next_action"] = "wait_for_wave3_runtime"
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
