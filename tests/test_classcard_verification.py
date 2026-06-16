from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from chat_lms_agent.classcard_db import WordRecord
from chat_lms_agent.classcard_plan import ClasscardMode, UploadPart, UploadPlan
from chat_lms_agent.classcard_verification import (
    ClasscardPartCheck,
    ClasscardVerificationResult,
    ClasscardVerificationStatus,
    record_verification_result,
    verify_class_page_text,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_verify_class_page_text_accepts_title_and_card_count_without_spacing() -> None:
    plan = _plan_with_word_count(123)

    result = verify_class_page_text(plan, "이지후 2026-06-14123 카드")

    assert result.status is ClasscardVerificationStatus.COMPLETED
    assert result.completed_indexes == (0,)
    assert result.checks[0].actual_count == 123


def test_record_verification_result_clears_stale_recovery_fields_on_completed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat_lms.db"
    checkpoint = tmp_path / "checkpoint.json"
    run_id = "run-1"
    _seed_run(db_path, run_id)
    checkpoint.write_text(
        json.dumps(
            {
                "status": "recovery_required",
                "last_error": "old failure",
                "headless_retry_required": True,
            },
        ),
        encoding="utf-8",
    )
    plan = _plan_with_word_count(1)
    verification = ClasscardVerificationResult(
        status=ClasscardVerificationStatus.COMPLETED,
        checks=(
            ClasscardPartCheck(
                index=0,
                title="이지후 2026-06-14",
                assigned_date="2026-06-14",
                expected_count=1,
                actual_count=1,
                matched_text="이지후 2026-06-141 카드",
                found=True,
            ),
        ),
        recovery_action="headless_missing_only_retry_then_operator_followup",
        operator_followup_required=False,
    )

    record_verification_result(plan, checkpoint, db_path, run_id, verification)

    checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    db_payload = _run_payload(db_path, run_id)
    assert checkpoint_payload["status"] == "completed"
    assert "last_error" not in checkpoint_payload
    assert "headless_retry_required" not in checkpoint_payload
    assert db_payload["verified"] == "true"
    assert db_payload["operator_followup_required"] == "false"
    assert "last_error" not in db_payload
    assert "headless_retry_required" not in db_payload


def _plan_with_word_count(word_count: int) -> UploadPlan:
    words = tuple(WordRecord(index, f"word{index}", "뜻") for index in range(word_count))
    part = UploadPart(
        index=0,
        label="전체",
        title="이지후 2026-06-14",
        assigned_date="2026-06-14",
        words=words,
    )
    return UploadPlan(
        student_id=2,
        student_name="이지후",
        target_class_name="이지후",
        lesson_id=17,
        lesson_date="2026-06-14",
        mode=ClasscardMode.ALL,
        parts=(part,),
    )


def _seed_run(db_path: Path, run_id: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE classcard_upload_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    conn.execute(
        "INSERT INTO classcard_upload_runs(run_id, status, payload_json) VALUES (?, ?, ?)",
        (
            run_id,
            "recovery_required",
            json.dumps(
                {
                    "last_error": "old failure",
                    "headless_retry_required": "true",
                    "operator_followup_required": "true",
                },
            ),
        ),
    )
    conn.commit()
    conn.close()


def _run_payload(db_path: Path, run_id: str) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT payload_json FROM classcard_upload_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    payload = json.loads(str(row[0]))
    assert isinstance(payload, dict)
    return payload
