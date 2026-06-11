from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import ProfileState

type KakaoMediaFetcher = Callable[[str], bytes]


def store_inbound_media(
    profile: ProfileState,
    *,
    contact_id: str,
    message_id: str,
    media_urls: tuple[str, ...],
    fetcher: KakaoMediaFetcher,
) -> tuple[str, ...]:
    refs: list[str] = []
    base_dir = _message_media_dir(profile, contact_id, message_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    for index, url in enumerate(media_urls):
        path = base_dir / f"{index}.bin"
        _ = path.write_bytes(fetcher(url))
        refs.append(_redacted_media_ref(contact_id, message_id, index))
    return tuple(refs)


def _message_media_dir(profile: ProfileState, contact_id: str, message_id: str) -> Path:
    return (
        profile.root
        / STATE_DIR
        / "kakao"
        / "media"
        / _safe_path_segment(contact_id)
        / _safe_path_segment(message_id)
    )


def _redacted_media_ref(contact_id: str, message_id: str, index: int) -> str:
    return (
        "<profile-root>/.chat-lms-state/kakao/media/"
        f"{_safe_path_segment(contact_id)}/{_safe_path_segment(message_id)}/{index}.bin"
    )


def _safe_path_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip("._")
    if cleaned:
        return cleaned[:96]
    return "item"
