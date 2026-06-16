from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class ClasscardCard:
    front: str
    back: str
    audio_path: str


@dataclass(frozen=True, slots=True)
class CardMismatch:
    index: int
    expected: ClasscardCard | None
    actual: ClasscardCard | None
    fields: tuple[str, ...]

    def summary(self) -> str:
        return f"card[{self.index}] fields={','.join(self.fields)} expected={self.expected} actual={self.actual}"


@dataclass(frozen=True, slots=True)
class ClasscardSetSummary:
    set_idx: str
    text: str


def normalize_audio_path(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    parsed = urlsplit(stripped)
    if parsed.scheme or parsed.netloc:
        return parsed.path
    return urlsplit(stripped).path


def card_mismatches(expected: tuple[ClasscardCard, ...], actual: tuple[ClasscardCard, ...]) -> tuple[CardMismatch, ...]:
    mismatches: list[CardMismatch] = []
    max_len = max(len(expected), len(actual))
    for index in range(max_len):
        if index >= len(expected):
            mismatches.append(CardMismatch(index=index, expected=None, actual=actual[index], fields=("extra_card",)))
            continue
        if index >= len(actual):
            mismatches.append(CardMismatch(index=index, expected=expected[index], actual=None, fields=("missing_card",)))
            continue
        expected_card = expected[index]
        actual_card = actual[index]
        fields: list[str] = []
        if expected_card.front.strip() != actual_card.front.strip():
            fields.append("front")
        if expected_card.back.strip() != actual_card.back.strip():
            fields.append("back")
        expected_audio_path = normalize_audio_path(expected_card.audio_path)
        actual_audio_path = normalize_audio_path(actual_card.audio_path)
        if expected_audio_path and expected_audio_path != actual_audio_path:
            fields.append("audio_path")
        if fields:
            mismatches.append(
                CardMismatch(
                    index=index,
                    expected=expected_card,
                    actual=actual_card,
                    fields=tuple(fields),
                )
            )
    return tuple(mismatches)


def mismatch_report(mismatches: tuple[CardMismatch, ...], *, limit: int = 5) -> str:
    visible = mismatches[:limit]
    suffix = "" if len(mismatches) <= limit else f" ... +{len(mismatches) - limit} more"
    return "; ".join(mismatch.summary() for mismatch in visible) + suffix


def cards_from_payload(payload: Iterable[Mapping[str, str]]) -> tuple[ClasscardCard, ...]:
    return tuple(
        ClasscardCard(
            front=str(card.get("front", "")),
            back=str(card.get("back", "")),
            audio_path=str(card.get("audio_path", "")),
        )
        for card in payload
    )


def sets_from_payload(payload: Iterable[Mapping[str, str]]) -> tuple[ClasscardSetSummary, ...]:
    return tuple(
        ClasscardSetSummary(
            set_idx=str(item.get("set_idx", "")),
            text=" ".join(str(item.get("text", "")).split()),
        )
        for item in payload
        if str(item.get("set_idx", "")).strip()
    )
