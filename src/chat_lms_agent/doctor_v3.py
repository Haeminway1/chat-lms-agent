from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from chat_lms_agent.hosts import active_host
from chat_lms_agent.route_packs import load_route_packs
from chat_lms_agent.side_panel_design_lint import side_panel_design_lint
from chat_lms_agent.state import ProfileState

V3CheckStatus = Literal["PASS", "FAIL", "UNSAFE"]

_LESSON_PANEL_ASSET_NAMES: Final = ("lesson_panel_server.py", "lesson_panel_view.html")
_ROUTE_PACK_WARNING_FALLBACK: Final = "unknown-route-pack.json"


@dataclass(frozen=True, slots=True)
class V3DoctorCheck:
    id: str
    status: V3CheckStatus
    message_ko: str
    repair_action: str | None
    safe_to_auto_repair: bool


def v3_doctor_checks(profile_state: ProfileState | str) -> tuple[V3DoctorCheck, ...]:
    match profile_state:
        case str() as repair_action:
            return (
                _unsafe("trace_journal", repair_action),
                _unsafe("audit_ledger", repair_action),
                _unsafe("approval_ledger", repair_action),
                _unsafe("academy_db_v3", repair_action),
            )
        case ProfileState() as profile:
            return (
                _pass("trace_journal", "trace journal boundary ready"),
                _pass("audit_ledger", "audit ledger boundary ready"),
                _pass("approval_ledger", "approval ledger boundary ready"),
                _pass("academy_db_v3", "academy DB V3 tool pack ready"),
                _lesson_panel_runtime_assets_check(profile),
                _side_panel_viewers_lint_check(profile),
                _route_pack_warnings_check(profile),
            )


def _pass(check_id: str, message: str) -> V3DoctorCheck:
    return V3DoctorCheck(
        id=check_id,
        status="PASS",
        message_ko=message,
        repair_action=None,
        safe_to_auto_repair=True,
    )


def _unsafe(check_id: str, repair_action: str) -> V3DoctorCheck:
    return V3DoctorCheck(
        id=check_id,
        status="UNSAFE",
        message_ko=f"{check_id} cannot use public repo state",
        repair_action=repair_action,
        safe_to_auto_repair=False,
    )


def _fail(
    check_id: str,
    message: str,
    repair_action: str,
    *,
    safe_to_auto_repair: bool,
) -> V3DoctorCheck:
    return V3DoctorCheck(
        id=check_id,
        status="FAIL",
        message_ko=message,
        repair_action=repair_action,
        safe_to_auto_repair=safe_to_auto_repair,
    )


def _lesson_panel_runtime_assets_check(profile: ProfileState) -> V3DoctorCheck:
    scripts_dir = profile.root / active_host().workspace_dirname / "scripts"
    missing = tuple(
        name for name in _LESSON_PANEL_ASSET_NAMES if not (scripts_dir / name).exists()
    )
    if not missing:
        return _pass(
            "lesson_panel_runtime_assets",
            "lesson panel runtime assets ready",
        )
    return _fail(
        "lesson_panel_runtime_assets",
        "lesson panel runtime assets missing: " + ", ".join(missing),
        "side-panel lesson install-assets --profile-root <profile-root> --json",
        safe_to_auto_repair=True,
    )


def _side_panel_viewers_lint_check(profile: ProfileState) -> V3DoctorCheck:
    scripts_dir = profile.root / active_host().workspace_dirname / "scripts"
    viewer_path = scripts_dir / "lesson_panel_view.html"
    if not viewer_path.exists():
        return _pass("side_panel_viewers_lint", "no installed side-panel viewers to lint")
    status_code, payload = side_panel_design_lint(viewer_path, "all")
    if status_code == 0:
        return _pass("side_panel_viewers_lint", "installed side-panel viewers pass design lint")
    errors = payload.get("errors")
    if isinstance(errors, list):
        detail = ", ".join(error for error in errors if isinstance(error, str))
    else:
        detail = "design lint failed"
    viewer_label = (
        f"<profile-root>/{active_host().workspace_dirname}/scripts/lesson_panel_view.html"
    )
    return _fail(
        "side_panel_viewers_lint",
        "installed side-panel viewer lint failed: lesson_panel_view.html: " + detail,
        "side-panel design lint --artifact " + viewer_label + " --mode all --json",
        safe_to_auto_repair=False,
    )


def _route_pack_warnings_check(profile: ProfileState) -> V3DoctorCheck:
    _packs, warnings = load_route_packs(profile.repo_root, profile)
    if not warnings:
        return _pass("route_pack_warnings", "route packs parse cleanly")
    file_names = tuple(_route_pack_warning_file_name(warning) for warning in warnings)
    return _fail(
        "route_pack_warnings",
        "route pack warnings: " + ", ".join(warnings),
        "fix route pack files: " + ", ".join(file_names),
        safe_to_auto_repair=False,
    )


def _route_pack_warning_file_name(warning: str) -> str:
    raw_file_name = warning.partition(":")[0].strip()
    file_name = raw_file_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if file_name:
        return file_name
    return _ROUTE_PACK_WARNING_FALLBACK
