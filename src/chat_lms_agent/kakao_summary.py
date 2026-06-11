from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Literal, cast

from chat_lms_agent.state import STATE_DIR, JsonValue, redact_text

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import ProfileState

KakaoSummarySource = Literal["generated", "fallback"]


@dataclass(frozen=True, slots=True)
class KakaoGeneratedSummary:
    contact_id: str
    summary_text: str
    generated_at: str
    model_id: str
    through_message_id: str


def store_generated_chat_summary(
    profile: ProfileState,
    *,
    summary: KakaoGeneratedSummary,
) -> KakaoGeneratedSummary:
    record = KakaoGeneratedSummary(
        contact_id=summary.contact_id,
        summary_text=redact_text(summary.summary_text),
        generated_at=summary.generated_at,
        model_id=summary.model_id,
        through_message_id=summary.through_message_id,
    )
    store = _read_summary_store(profile)
    store[record.contact_id] = _summary_to_json(record)
    _write_summary_store(profile, store)
    return record


def load_generated_chat_summary(
    profile: ProfileState,
    *,
    contact_id: str,
) -> KakaoGeneratedSummary | None:
    payload = _read_summary_store(profile).get(contact_id)
    if not isinstance(payload, dict):
        return None
    return _summary_from_json(payload)


def fallback_summary_text(
    *,
    message_count: int,
    inbound_count: int,
    outbound_count: int,
    last_message_text: str,
) -> str:
    compact_last = " ".join(last_message_text.split())
    if not compact_last:
        return f"{message_count} messages (inbound {inbound_count}, outbound {outbound_count})."
    return (
        f"{message_count} messages (inbound {inbound_count}, outbound {outbound_count}). "
        f"Last: {compact_last}"
    )


def _summary_store_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "kakao" / "summaries.json"


def _read_summary_store(profile: ProfileState) -> dict[str, JsonValue]:
    path = _summary_store_path(profile)
    if not path.exists():
        return {}
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _write_summary_store(profile: ProfileState, store: dict[str, JsonValue]) -> None:
    path = _summary_store_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _summary_to_json(record: KakaoGeneratedSummary) -> dict[str, JsonValue]:
    return {
        "contact_id": record.contact_id,
        "summary_text": record.summary_text,
        "generated_at": record.generated_at,
        "model_id": record.model_id,
        "through_message_id": record.through_message_id,
    }


def _summary_from_json(payload: dict[str, JsonValue]) -> KakaoGeneratedSummary | None:
    contact_id = payload.get("contact_id")
    summary_text = payload.get("summary_text")
    generated_at = payload.get("generated_at")
    model_id = payload.get("model_id")
    through_message_id = payload.get("through_message_id")
    if not (
        isinstance(contact_id, str)
        and isinstance(summary_text, str)
        and isinstance(generated_at, str)
        and isinstance(model_id, str)
        and isinstance(through_message_id, str)
    ):
        return None
    return KakaoGeneratedSummary(
        contact_id=contact_id,
        summary_text=summary_text,
        generated_at=generated_at,
        model_id=model_id,
        through_message_id=through_message_id,
    )
