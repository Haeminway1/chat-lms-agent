from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from chat_lms_agent.state import ProfileState

V3CheckStatus = Literal["PASS", "UNSAFE"]


@dataclass(frozen=True, slots=True)
class V3DoctorCheck:
    id: str
    status: V3CheckStatus
    message_ko: str
    repair_action: str | None
    safe_to_auto_repair: bool


def v3_doctor_checks(profile_state: ProfileState | str) -> tuple[V3DoctorCheck, ...]:
    if isinstance(profile_state, str):
        return (
            _unsafe("trace_journal", profile_state),
            _unsafe("audit_ledger", profile_state),
            _unsafe("approval_ledger", profile_state),
            _unsafe("academy_db_v3", profile_state),
        )
    return (
        _pass("trace_journal", "trace journal boundary ready"),
        _pass("audit_ledger", "audit ledger boundary ready"),
        _pass("approval_ledger", "approval ledger boundary ready"),
        _pass("academy_db_v3", "academy DB V3 tool pack ready"),
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
