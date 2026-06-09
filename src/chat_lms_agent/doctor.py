from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypedDict

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


class DoctorCheckPayload(TypedDict):
    id: str
    status: str
    message_ko: str
    repair_action: str | None
    safe_to_auto_repair: bool


class DoctorPayload(TypedDict):
    status: str
    exit_code: int
    checks: list[DoctorCheckPayload]
    needs_approval: list[str]
    repair_failed: list[str]


def build_doctor_report(repo_root: Path) -> DoctorReport:
    checks = tuple(
        _path_check(repo_root, check_id, path, message)
        for check_id, path, message in REQUIRED_PATHS
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
    return DoctorReport(
        status="PASS",
        exit_code=0,
        checks=checks,
        needs_approval=(),
        repair_failed=(),
    )


def report_to_jsonable(report: DoctorReport) -> DoctorPayload:
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
