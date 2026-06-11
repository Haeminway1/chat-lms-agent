from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Literal, cast

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

KakaoDirection = Literal["inbound", "outbound"]


@dataclass(frozen=True, slots=True)
class KakaoChatMessage:
    message_id: str
    direction: KakaoDirection
    text: str
    sent_at: str


@dataclass(frozen=True, slots=True)
class KakaoIngestResult:
    contact_id: str
    message_count: int
    new_count: int


@dataclass(frozen=True, slots=True)
class KakaoChatSummary:
    contact_id: str
    message_count: int
    inbound_count: int
    outbound_count: int
    last_message_text: str


def ingest_chat_history(
    profile: ProfileState,
    *,
    contact_id: str,
    messages: tuple[KakaoChatMessage, ...],
) -> KakaoIngestResult:
    store = _read_store(profile)
    existing = _messages_for_contact(store, contact_id)
    seen = {message.message_id for message in existing}
    merged = [*existing]
    new_count = 0
    for message in messages:
        if message.message_id in seen:
            continue
        merged.append(message)
        seen.add(message.message_id)
        new_count += 1
    store[contact_id] = [_message_to_json(message) for message in merged]
    _write_store(profile, store)
    return KakaoIngestResult(contact_id=contact_id, message_count=len(merged), new_count=new_count)


def load_chat_history(profile: ProfileState, *, contact_id: str) -> tuple[KakaoChatMessage, ...]:
    return tuple(_messages_for_contact(_read_store(profile), contact_id))


def summarize_chat_history(profile: ProfileState, *, contact_id: str) -> KakaoChatSummary:
    messages = load_chat_history(profile, contact_id=contact_id)
    inbound = sum(1 for message in messages if message.direction == "inbound")
    outbound = sum(1 for message in messages if message.direction == "outbound")
    last_text = messages[-1].text if messages else ""
    return KakaoChatSummary(
        contact_id=contact_id,
        message_count=len(messages),
        inbound_count=inbound,
        outbound_count=outbound,
        last_message_text=last_text,
    )


def kakao_state_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "kakao"


def _chat_store_path(profile: ProfileState) -> Path:
    return kakao_state_dir(profile) / "chats.json"


def _read_store(profile: ProfileState) -> dict[str, JsonValue]:
    path = _chat_store_path(profile)
    if not path.exists():
        return {}
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _write_store(profile: ProfileState, store: dict[str, JsonValue]) -> None:
    path = _chat_store_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _messages_for_contact(
    store: dict[str, JsonValue],
    contact_id: str,
) -> tuple[KakaoChatMessage, ...]:
    raw_messages = store.get(contact_id)
    if not isinstance(raw_messages, list):
        return ()
    messages: list[KakaoChatMessage] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        parsed = _message_from_json(item)
        if parsed is not None:
            messages.append(parsed)
    return tuple(messages)


def _message_from_json(payload: dict[str, JsonValue]) -> KakaoChatMessage | None:
    message_id = payload.get("message_id")
    direction = payload.get("direction")
    text = payload.get("text")
    sent_at = payload.get("sent_at")
    if not (isinstance(message_id, str) and isinstance(text, str) and isinstance(sent_at, str)):
        return None
    match direction:
        case "inbound" | "outbound":
            parsed_direction = direction
        case _:
            return None
    return KakaoChatMessage(
        message_id=message_id,
        direction=parsed_direction,
        text=text,
        sent_at=sent_at,
    )


def _message_to_json(message: KakaoChatMessage) -> dict[str, JsonValue]:
    return {
        "message_id": message.message_id,
        "direction": message.direction,
        "text": message.text,
        "sent_at": message.sent_at,
    }
