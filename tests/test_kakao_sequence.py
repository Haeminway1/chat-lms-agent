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

    def open_message_composer(self) -> None:
        return None

    def send_friend_message(self, recipient: str, part_index: int, text: str) -> None:
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
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert saved["completed_part_indexes"] == [0, 1]
    assert saved["status"] == "completed"
