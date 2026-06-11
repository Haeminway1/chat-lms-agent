from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from chat_lms_agent.kakao_plan import build_send_plan
from chat_lms_agent.kakao_send import run_kakao_send_sequence

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class _RecordingKakaoPage:
    sent: list[tuple[int, str, str]] = field(default_factory=list)
    fail_on_part_index: int | None = None

    def open_message_composer(self) -> None:
        return None

    def send_friend_message(self, recipient: str, part_index: int, text: str) -> None:
        if self.fail_on_part_index == part_index:
            raise RuntimeError
        self.sent.append((part_index, recipient, text))


def test_send_sequence_resumes_from_checkpoint_without_replaying_completed_parts(
    tmp_path: Path,
) -> None:
    # Given: a two-part send plan whose first part is already checkpointed.
    checkpoint = tmp_path / "kakao.checkpoint.json"
    checkpoint.write_text(
        json.dumps({"completed_part_indexes": [0]}, ensure_ascii=False),
        encoding="utf-8",
    )
    plan = build_send_plan(
        recipient="friend-group:parents",
        message=("a" * 400) + ("b" * 50),
        max_parts_per_run=10,
    )
    page = _RecordingKakaoPage()

    # When: the sequence resumes from the checkpoint.
    result = run_kakao_send_sequence(plan, page, checkpoint)

    # Then: only the missing part is sent and the checkpoint is complete.
    assert page.sent == [(1, "friend-group:parents", "b" * 50)]
    assert result.status == "completed"
    assert result.completed_part_indexes == (0, 1)
    assert result.sent_part_indexes == (1,)
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert saved["completed_part_indexes"] == [0, 1]
    assert saved["status"] == "completed"


def test_send_sequence_reports_no_new_parts_when_checkpoint_already_complete(
    tmp_path: Path,
) -> None:
    # Given: every send-plan part is already checkpointed.
    checkpoint = tmp_path / "kakao.checkpoint.json"
    checkpoint.write_text(
        json.dumps({"completed_part_indexes": [0, 1]}, ensure_ascii=False),
        encoding="utf-8",
    )
    plan = build_send_plan(
        recipient="friend-group:parents",
        message=("a" * 400) + ("b" * 50),
        max_parts_per_run=10,
    )
    page = _RecordingKakaoPage()

    # When: the sequence is invoked again.
    result = run_kakao_send_sequence(plan, page, checkpoint)

    # Then: nothing is resent and quota callers can see no new work happened.
    assert page.sent == []
    assert result.status == "completed"
    assert result.completed_part_indexes == (0, 1)
    assert result.sent_part_indexes == ()


def test_send_sequence_reports_no_new_parts_for_failed_missing_part(tmp_path: Path) -> None:
    # Given: a resumed plan where the next missing part fails before completion.
    checkpoint = tmp_path / "kakao.checkpoint.json"
    checkpoint.write_text(
        json.dumps({"completed_part_indexes": [0]}, ensure_ascii=False),
        encoding="utf-8",
    )
    plan = build_send_plan(
        recipient="friend-group:parents",
        message=("a" * 400) + ("b" * 50),
        max_parts_per_run=10,
    )
    page = _RecordingKakaoPage(fail_on_part_index=1)

    # When: the send sequence fails on the missing part.
    result = run_kakao_send_sequence(plan, page, checkpoint)

    # Then: the preexisting checkpoint remains and no new quota part is reportable.
    assert result.status == "failed"
    assert result.completed_part_indexes == (0,)
    assert result.sent_part_indexes == ()
