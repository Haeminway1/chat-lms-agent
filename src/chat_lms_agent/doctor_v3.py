from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal

from chat_lms_agent.hosts import active_host
from chat_lms_agent.route_packs import load_route_packs
from chat_lms_agent.side_panel_design_promotion import (
    InstalledDesignViewer,
    installed_design_viewers,
)
from chat_lms_agent.state import ProfileState

V3CheckStatus = Literal["PASS", "FAIL", "UNSAFE"]

_ROUTE_PACK_WARNING_FALLBACK: Final = "unknown-route-pack.json"
_VERIFY_EVIDENCE_MAX_AGE_DAYS: Final = 7


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
                _side_panel_viewers_verify_evidence_check(profile),
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


def _side_panel_viewers_verify_evidence_check(profile: ProfileState) -> V3DoctorCheck:
    viewers = installed_design_viewers(profile)
    if not viewers:
        return _pass(
            "side_panel_viewers_verify_evidence",
            "no installed side-panel viewers to verify",
        )
    for viewer in viewers:
        failure = _verify_evidence_failure(viewer)
        if failure is not None:
            return _fail(
                "side_panel_viewers_verify_evidence",
                "installed side-panel viewer verify evidence " + failure,
                _verify_evidence_repair_action(viewer),
                safe_to_auto_repair=False,
            )
    return _pass(
        "side_panel_viewers_verify_evidence",
        "installed side-panel viewer verify evidence is fresh",
    )


def _verify_evidence_failure(viewer: InstalledDesignViewer) -> str | None:
    timestamp = _parse_timestamp(viewer.verify_evidence_timestamp_utc)
    if timestamp is None:
        return "timestamp is invalid"
    now = datetime.now(tz=UTC)
    if timestamp > now:
        return "timestamp is in the future"
    if now - timestamp > timedelta(days=_VERIFY_EVIDENCE_MAX_AGE_DAYS):
        return f"is stale; rerun within {_VERIFY_EVIDENCE_MAX_AGE_DAYS} days"
    if viewer.verify_evidence_path is None or not viewer.verify_evidence_path.exists():
        return "JSON is missing"
    return None


def _parse_timestamp(raw_timestamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw_timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _verify_evidence_repair_action(viewer: InstalledDesignViewer) -> str:
    artifact = f"<profile-root>/{active_host().workspace_dirname}/scripts/{viewer.view}_view.html"
    return (
        f"side-panel design verify --artifact {artifact} "
        f"--view {viewer.view} --mode all --json"
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
