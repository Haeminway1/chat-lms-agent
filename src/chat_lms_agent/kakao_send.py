from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.kakao_channel_page import KakaoChannelPage
    from chat_lms_agent.kakao_plan import KakaoSendPlan
    from chat_lms_agent.state import JsonValue

KakaoSendStatus = Literal["completed", "failed"]


@dataclass(frozen=True, slots=True)
class KakaoSendResult:
    status: KakaoSendStatus
    completed_part_indexes: tuple[int, ...]
    sent_part_indexes: tuple[int, ...]


def run_kakao_send_sequence(
    plan: KakaoSendPlan,
    page: KakaoChannelPage,
    checkpoint_path: Path,
) -> KakaoSendResult:
    completed = set(_completed_indexes(checkpoint_path))
    sent: list[int] = []
    missing_parts = tuple(part for part in plan.parts if part.index not in completed)
    if missing_parts:
        page.open_message_composer()
    try:
        for part in missing_parts:
            page.send_friend_message(plan.recipient, part.index, part.text)
            completed.add(part.index)
            sent.append(part.index)
            _write_checkpoint(checkpoint_path, "part_completed", completed)
    except RuntimeError:
        _write_checkpoint(checkpoint_path, "failed", completed)
        return KakaoSendResult("failed", tuple(sorted(completed)), tuple(sent))
    _write_checkpoint(checkpoint_path, "completed", completed)
    return KakaoSendResult("completed", tuple(sorted(completed)), tuple(sent))


def _completed_indexes(path: Path) -> tuple[int, ...]:
    if not path.exists():
        return ()
    try:
        raw = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return ()
    if not isinstance(raw, dict):
        return ()
    indexes = raw.get("completed_part_indexes")
    if not isinstance(indexes, list):
        return ()
    return tuple(item for item in indexes if isinstance(item, int) and not isinstance(item, bool))


def _write_checkpoint(path: Path, status: str, completed: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    completed_values: list[JsonValue] = []
    completed_values.extend(sorted(completed))
    payload: dict[str, JsonValue] = {
        "schema_version": "kakao-send-checkpoint-v1",
        "status": status,
        "completed_part_indexes": completed_values,
    }
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)
