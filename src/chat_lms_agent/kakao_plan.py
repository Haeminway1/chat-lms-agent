from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

MAX_BASIC_TEXT_CHARS: Final = 400
DEFAULT_MAX_PARTS_PER_RUN: Final = 20
DEFAULT_PACING_SECONDS: Final = 3
MAX_BUTTONS: Final = 2
EMPTY_MESSAGE_ERROR: Final = "KAKAO_EMPTY_MESSAGE"
INVALID_RUN_CAP_ERROR: Final = "KAKAO_INVALID_RUN_CAP"
INVALID_PACING_ERROR: Final = "KAKAO_INVALID_PACING"
TOO_MANY_BUTTONS_ERROR: Final = "KAKAO_TOO_MANY_BUTTONS"
EMPTY_MESSAGE_TEXT: Final = "Kakao message body is empty"
INVALID_RUN_CAP_TEXT: Final = "--max must be positive"
INVALID_PACING_TEXT: Final = "pacing seconds cannot be negative"
TOO_MANY_BUTTONS_TEXT: Final = "Kakao messages allow at most two buttons"


@dataclass(frozen=True, slots=True)
class KakaoPlanError(Exception):
    error_code: str
    message: str


@dataclass(frozen=True, slots=True)
class KakaoButton:
    label: str
    url: str


@dataclass(frozen=True, slots=True)
class KakaoSendPart:
    index: int
    text: str


@dataclass(frozen=True, slots=True)
class KakaoSendPlan:
    recipient: str
    parts: tuple[KakaoSendPart, ...]
    total_parts: int
    capped: bool
    pacing_seconds: int
    image_path: Path | None
    buttons: tuple[KakaoButton, ...]


def build_send_plan(  # noqa: PLR0913 - CLI-shaped boundary
    *,
    recipient: str,
    message: str,
    max_parts_per_run: int = DEFAULT_MAX_PARTS_PER_RUN,
    pacing_seconds: int = DEFAULT_PACING_SECONDS,
    image_path: Path | None = None,
    buttons: tuple[KakaoButton, ...] = (),
) -> KakaoSendPlan:
    normalized = message.strip()
    if not normalized:
        raise KakaoPlanError(EMPTY_MESSAGE_ERROR, EMPTY_MESSAGE_TEXT)
    if max_parts_per_run <= 0:
        raise KakaoPlanError(INVALID_RUN_CAP_ERROR, INVALID_RUN_CAP_TEXT)
    if pacing_seconds < 0:
        raise KakaoPlanError(INVALID_PACING_ERROR, INVALID_PACING_TEXT)
    if len(buttons) > MAX_BUTTONS:
        raise KakaoPlanError(TOO_MANY_BUTTONS_ERROR, TOO_MANY_BUTTONS_TEXT)

    chunks = _chunks(normalized, MAX_BASIC_TEXT_CHARS)
    selected = chunks[:max_parts_per_run]
    parts = tuple(KakaoSendPart(index=index, text=text) for index, text in enumerate(selected))
    return KakaoSendPlan(
        recipient=recipient,
        parts=parts,
        total_parts=len(chunks),
        capped=len(selected) < len(chunks),
        pacing_seconds=pacing_seconds,
        image_path=image_path,
        buttons=buttons,
    )


def _chunks(value: str, size: int) -> tuple[str, ...]:
    return tuple(value[index : index + size] for index in range(0, len(value), size))
