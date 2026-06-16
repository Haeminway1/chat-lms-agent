from __future__ import annotations

import json
import re
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from chat_lms_agent.classcard_db import connect
from chat_lms_agent.classcard_plan import UploadPart, UploadPlan


class ClasscardVerificationStatus(StrEnum):
    COMPLETED = "completed"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True, slots=True)
class ClasscardPartCheck:
    index: int
    title: str
    assigned_date: str
    expected_count: int
    actual_count: int | None
    matched_text: str | None
    found: bool


@dataclass(frozen=True, slots=True)
class ClasscardVerificationResult:
    status: ClasscardVerificationStatus
    checks: tuple[ClasscardPartCheck, ...]
    recovery_action: str
    operator_followup_required: bool

    @property
    def completed_indexes(self) -> tuple[int, ...]:
        return tuple(check.index for check in self.checks if check.found)

    @property
    def missing_indexes(self) -> tuple[int, ...]:
        return tuple(check.index for check in self.checks if not check.found)


_COUNT_PATTERN = re.compile(r"(?P<count>\d+)\s*카드")
_KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
_RECOVERY_ACTION = "headless_missing_only_retry_then_operator_followup"


def classcard_date_label(assigned_date: str) -> str:
    day = date.fromisoformat(assigned_date)
    return f"{day:%m/%d}({_KOREAN_WEEKDAYS[day.weekday()]})"


def verify_class_page_text(plan: UploadPlan, page_text: str) -> ClasscardVerificationResult:
    lines = _normalized_lines(page_text)
    used_lines: set[int] = set()
    checks: list[ClasscardPartCheck] = []
    for part in plan.parts:
        match_index = _matching_line_index(plan.student_name, part, lines, used_lines)
        if match_index is None:
            checks.append(_missing_check(part))
            continue
        used_lines.add(match_index)
        checks.append(_found_check(part, lines[match_index]))
    status = (
        ClasscardVerificationStatus.COMPLETED
        if all(check.found for check in checks)
        else ClasscardVerificationStatus.RECOVERY_REQUIRED
    )
    return ClasscardVerificationResult(
        status=status,
        checks=tuple(checks),
        recovery_action=_RECOVERY_ACTION,
        operator_followup_required=status is ClasscardVerificationStatus.RECOVERY_REQUIRED,
    )


def mark_recovery_required(
    plan: UploadPlan,
    checkpoint_path: str | Path,
    db_path: str | Path,
    run_id: str,
    failure_reason: str,
) -> None:
    checkpoint = Path(checkpoint_path)
    payload = _read_checkpoint(checkpoint)
    completed = _completed_indexes_from_payload(payload)
    missing = tuple(part.index for part in plan.parts if part.index not in completed)
    _write_recovery_checkpoint(
        checkpoint,
        plan,
        completed_indexes=completed,
        missing_indexes=missing,
        failure_reason=failure_reason,
    )
    _update_db_run(
        db_path,
        run_id,
        ClasscardVerificationStatus.RECOVERY_REQUIRED.value,
        {
            "last_error": failure_reason,
            "missing_indexes": [str(index) for index in missing],
            "recovery_action": _RECOVERY_ACTION,
            "operator_followup_required": "true",
        },
    )


def record_verification_result(
    plan: UploadPlan,
    checkpoint_path: str | Path,
    db_path: str | Path,
    run_id: str,
    verification: ClasscardVerificationResult,
) -> None:
    checkpoint = Path(checkpoint_path)
    payload = _read_checkpoint(checkpoint)
    payload.update(_verification_payload(plan, verification))
    if verification.status is ClasscardVerificationStatus.COMPLETED:
        _clear_recovery_fields(payload)
    checkpoint.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _update_db_run(
        db_path,
        run_id,
        verification.status.value,
        {
            "verified": "true",
            "missing_indexes": [str(index) for index in verification.missing_indexes],
            "recovery_action": verification.recovery_action,
            "operator_followup_required": str(verification.operator_followup_required).lower(),
            "last_error": None,
            "headless_retry_required": None,
        },
    )


def _normalized_lines(page_text: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in page_text.splitlines() if line.strip())


def _matching_line_index(student_name: str, part: UploadPart, lines: tuple[str, ...], used_lines: set[int]) -> int | None:
    for index, line in enumerate(lines):
        if index in used_lines:
            continue
        if _line_matches_part(student_name, part, line):
            return index
    return None


def _line_matches_part(student_name: str, part: UploadPart, line: str) -> bool:
    if student_name not in line:
        return False
    if classcard_date_label(part.assigned_date) not in line and part.assigned_date not in line:
        return False
    if _label_required(part.label) and part.label not in line and part.title not in line:
        return False
    return _count_from_line(line, part=part) == len(part.words)


def _label_required(label: str) -> bool:
    return label != "전체" and not (label.startswith("D") and label[1:].isdigit())


def _count_from_line(line: str, part: UploadPart | None = None) -> int | None:
    if part is not None:
        compact_line = "".join(line.split())
        compact_title = "".join(part.title.split())
        expected_count = len(part.words)
        if f"{compact_title}{expected_count}카드" in compact_line:
            return expected_count
    match = _COUNT_PATTERN.search(line)
    if match is None:
        return None
    return int(match.group("count"))


def _found_check(part: UploadPart, matched_text: str) -> ClasscardPartCheck:
    return ClasscardPartCheck(
        index=part.index,
        title=part.title,
        assigned_date=part.assigned_date,
        expected_count=len(part.words),
        actual_count=_count_from_line(matched_text, part=part),
        matched_text=matched_text,
        found=True,
    )


def _missing_check(part: UploadPart) -> ClasscardPartCheck:
    return ClasscardPartCheck(
        index=part.index,
        title=part.title,
        assigned_date=part.assigned_date,
        expected_count=len(part.words),
        actual_count=None,
        matched_text=None,
        found=False,
    )


def _write_recovery_checkpoint(
    checkpoint: Path,
    plan: UploadPlan,
    *,
    completed_indexes: tuple[int, ...],
    missing_indexes: tuple[int, ...],
    failure_reason: str,
) -> None:
    payload = _read_checkpoint(checkpoint)
    payload.update({
        "status": ClasscardVerificationStatus.RECOVERY_REQUIRED.value,
        "student": plan.student_name,
        "target_class_name": plan.target_class_name,
        "lesson_date": plan.lesson_date,
        "mode": plan.mode.value,
        "completed_indexes": list(completed_indexes),
        "missing_indexes": list(missing_indexes),
        "current_part": missing_indexes[0] if missing_indexes else None,
        "last_error": failure_reason,
        "recovery_action": _RECOVERY_ACTION,
        "headless_retry_required": True,
        "operator_followup_required": True,
    })
    checkpoint.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _verification_payload(plan: UploadPlan, verification: ClasscardVerificationResult) -> dict[str, str | int | bool | list[int] | list[dict[str, str | int | bool | None]] | None]:
    return {
        "status": verification.status.value,
        "student": plan.student_name,
        "target_class_name": plan.target_class_name,
        "lesson_date": plan.lesson_date,
        "mode": plan.mode.value,
        "completed_indexes": list(verification.completed_indexes),
        "missing_indexes": list(verification.missing_indexes),
        "current_part": verification.missing_indexes[0] if verification.missing_indexes else None,
        "recovery_action": verification.recovery_action,
        "operator_followup_required": verification.operator_followup_required,
        "verification": [
            {
                "index": check.index,
                "title": check.title,
                "assigned_date": check.assigned_date,
                "expected_count": check.expected_count,
                "actual_count": check.actual_count,
                "matched_text": check.matched_text,
                "found": check.found,
            }
            for check in verification.checks
        ],
    }


def _read_checkpoint(checkpoint: Path) -> dict[str, str | int | bool | list[int] | list[str] | None]:
    if not checkpoint.exists():
        return {}
    raw = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items()}


def _completed_indexes_from_payload(payload: dict[str, str | int | bool | list[int] | list[str] | None]) -> tuple[int, ...]:
    raw = payload.get("completed_indexes")
    if not isinstance(raw, list):
        return ()
    return tuple(int(value) for value in raw)


def _clear_recovery_fields(payload: dict[str, object]) -> None:
    for key in ("last_error", "headless_retry_required"):
        payload.pop(key, None)


def _update_db_run(db_path: str | Path, run_id: str, status: str, updates: dict[str, str | list[str] | None]) -> None:
    with closing(connect(db_path)) as conn:
        row = conn.execute("SELECT payload_json FROM classcard_upload_runs WHERE run_id = ?", (run_id,)).fetchone()
        payload = json.loads(str(row["payload_json"])) if row is not None else {}
        if not isinstance(payload, dict):
            payload = {}
        for key, value in updates.items():
            if value is None:
                payload.pop(key, None)
            else:
                payload[key] = value
        conn.execute(
            "UPDATE classcard_upload_runs SET status = ?, payload_json = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
            (status, json.dumps(payload, ensure_ascii=False, sort_keys=True), run_id),
        )
        conn.commit()
