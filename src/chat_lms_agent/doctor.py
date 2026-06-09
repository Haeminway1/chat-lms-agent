from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Final, Literal, cast

from chat_lms_agent.academy_db import store_path
from chat_lms_agent.agent_tools import default_agent_tools
from chat_lms_agent.doctor_v3 import v3_doctor_checks
from chat_lms_agent.memory_obligations import obligations_for_reason
from chat_lms_agent.state import JsonValue, ProfileState, load_memory, resolve_profile_state

DoctorStatus = Literal["PASS", "REPAIRED", "NEEDS_APPROVAL", "REPAIR_FAILED", "UNSAFE"]
CheckStatus = Literal["PASS", "REPAIRED", "NEEDS_APPROVAL", "REPAIR_FAILED", "UNSAFE"]


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    id: str
    status: CheckStatus
    message_ko: str
    repair_action: str | None
    safe_to_auto_repair: bool


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: DoctorStatus
    exit_code: int
    checks: tuple[DoctorCheck, ...]
    needs_approval: tuple[str, ...]
    repair_failed: tuple[str, ...]


REQUIRED_PATHS: Final = (
    ("package", Path("src/chat_lms_agent/__init__.py"), "package contract ready"),
    ("plugin", Path(".codex-plugin/plugin.json"), "Codex plugin manifest ready"),
    ("skills", Path(".agents/skills/chat-lms-onboarding/SKILL.md"), "onboarding skill ready"),
    ("hooks", Path("hooks/hooks.json"), "Codex hooks ready"),
    (
        "side_panel",
        Path("docs/side-panel-design-reference.md"),
        "side-panel design reference ready",
    ),
)


def build_doctor_report(
    repo_root: Path,
    profile_root: str | None = None,
    profile: str | None = None,
) -> DoctorReport:
    profile_state = resolve_profile_state(repo_root, profile_root, profile)
    checks = (
        *tuple(
            _path_check(repo_root, check_id, path, message)
            for check_id, path, message in REQUIRED_PATHS
        ),
        _agent_tools_check(repo_root),
        _hooks_lifecycle_check(repo_root),
        _runtime_boundary_check(profile_state),
        _academy_db_check(profile_state),
        _memory_obligations_check(profile_state),
        *tuple(
            DoctorCheck(
                id=check.id,
                status=check.status,
                message_ko=check.message_ko,
                repair_action=check.repair_action,
                safe_to_auto_repair=check.safe_to_auto_repair,
            )
            for check in v3_doctor_checks(profile_state)
        ),
    )
    unsafe = tuple(check.id for check in checks if check.status == "UNSAFE")
    if unsafe:
        return DoctorReport(
            status="UNSAFE",
            exit_code=4,
            checks=checks,
            needs_approval=(),
            repair_failed=(),
        )
    failed = tuple(check.id for check in checks if check.status == "REPAIR_FAILED")
    if failed:
        return DoctorReport(
            status="REPAIR_FAILED",
            exit_code=2,
            checks=checks,
            needs_approval=(),
            repair_failed=failed,
        )
    needs_approval = tuple(check.id for check in checks if check.status == "NEEDS_APPROVAL")
    if needs_approval:
        return DoctorReport(
            status="NEEDS_APPROVAL",
            exit_code=5,
            checks=checks,
            needs_approval=needs_approval,
            repair_failed=(),
        )
    return DoctorReport(
        status="PASS",
        exit_code=0,
        checks=checks,
        needs_approval=(),
        repair_failed=(),
    )


def report_to_jsonable(report: DoctorReport) -> dict[str, JsonValue]:
    return {
        "status": report.status,
        "exit_code": report.exit_code,
        "checks": [
            {
                "id": check.id,
                "status": check.status,
                "message_ko": check.message_ko,
                "repair_action": check.repair_action,
                "safe_to_auto_repair": check.safe_to_auto_repair,
            }
            for check in report.checks
        ],
        "needs_approval": list(report.needs_approval),
        "repair_failed": list(report.repair_failed),
    }


def _path_check(repo_root: Path, check_id: str, path: Path, message: str) -> DoctorCheck:
    if (repo_root / path).exists():
        return DoctorCheck(
            id=check_id,
            status="PASS",
            message_ko=message,
            repair_action=None,
            safe_to_auto_repair=True,
        )
    return DoctorCheck(
        id=check_id,
        status="REPAIR_FAILED",
        message_ko=f"{message} missing",
        repair_action=f"create {path.as_posix()}",
        safe_to_auto_repair=True,
    )


def _agent_tools_check(repo_root: Path) -> DoctorCheck:
    tool_ids = {tool["id"] for tool in default_agent_tools()}
    docs_ready = (repo_root / "docs" / "agent-tool-registry.md").exists()
    if {"side-panel", "academy-db"}.issubset(tool_ids) and docs_ready:
        return DoctorCheck(
            id="agent_tools",
            status="PASS",
            message_ko="agent tool registry ready",
            repair_action=None,
            safe_to_auto_repair=True,
        )
    return DoctorCheck(
        id="agent_tools",
        status="REPAIR_FAILED",
        message_ko="agent tool registry missing required foundation tools or docs",
        repair_action="create docs/agent-tool-registry.md and register foundation tools",
        safe_to_auto_repair=True,
    )


def _hooks_lifecycle_check(repo_root: Path) -> DoctorCheck:
    hooks_path = repo_root / "hooks" / "hooks.json"
    required = {"SessionStart", "UserPromptSubmit", "PostToolUse", "PostCompact", "Stop"}
    try:
        payload = cast("JsonValue", json.loads(hooks_path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        payload = {}
    registered: set[str] = set(payload) if isinstance(payload, dict) else set()
    if required <= registered:
        return DoctorCheck(
            id="hooks_lifecycle",
            status="PASS",
            message_ko="full hook lifecycle ready",
            repair_action=None,
            safe_to_auto_repair=True,
        )
    return DoctorCheck(
        id="hooks_lifecycle",
        status="REPAIR_FAILED",
        message_ko="full hook lifecycle missing",
        repair_action="register SessionStart/UserPromptSubmit/PostToolUse/PostCompact/Stop",
        safe_to_auto_repair=True,
    )


def _runtime_boundary_check(profile_state: ProfileState | str) -> DoctorCheck:
    if isinstance(profile_state, str):
        return DoctorCheck(
            id="runtime_boundary",
            status="UNSAFE",
            message_ko="runtime profile state cannot use public repo root",
            repair_action=profile_state,
            safe_to_auto_repair=False,
        )
    return DoctorCheck(
        id="runtime_boundary",
        status="PASS",
        message_ko="runtime artifact boundary ready",
        repair_action=None,
        safe_to_auto_repair=True,
    )


def _academy_db_check(profile_state: ProfileState | str) -> DoctorCheck:
    if isinstance(profile_state, str):
        return DoctorCheck(
            id="academy_db",
            status="UNSAFE",
            message_ko="academy DB profile root is unsafe",
            repair_action=profile_state,
            safe_to_auto_repair=False,
        )
    if store_path(profile_state).exists():
        message = "academy DB initialized under private profile state"
    else:
        message = "academy DB CLI ready"
    return DoctorCheck(
        id="academy_db",
        status="PASS",
        message_ko=message,
        repair_action=None,
        safe_to_auto_repair=True,
    )


def _memory_obligations_check(profile_state: ProfileState | str) -> DoctorCheck:
    if isinstance(profile_state, str):
        return DoctorCheck(
            id="memory_obligations",
            status="UNSAFE",
            message_ko="memory obligation profile root is unsafe",
            repair_action=profile_state,
            safe_to_auto_repair=False,
        )
    memory_keys = {entry["key"] for entry in load_memory(profile_state)}
    missing = [
        obligation.key
        for obligation in obligations_for_reason("academy-db-init")
        if store_path(profile_state).exists() and obligation.key not in memory_keys
    ]
    if missing:
        return DoctorCheck(
            id="memory_obligations",
            status="NEEDS_APPROVAL",
            message_ko="memory obligations need explicit draft apply",
            repair_action="apply memory draft for " + ", ".join(missing),
            safe_to_auto_repair=False,
        )
    return DoctorCheck(
        id="memory_obligations",
        status="PASS",
        message_ko="memory obligation engine ready",
        repair_action=None,
        safe_to_auto_repair=True,
    )
