from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

from chat_lms_agent.route_packs import load_route_packs

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

ROUTE_CATALOG_BYTE_CEILING: Final = 2600
WEAK_ROUTE_CATALOG_SIGNALS: Final = frozenset(
    (
        "패널",
        "뷰어",
        "화면",
        "보드",
        "현황",
        "보고",
        "리포트",
        "목록",
        "리스트",
        "열어",
        "보여",
        "띄워",
        "수업",
        "단어",
        "학생",
        "panel",
        "viewer",
        "dashboard",
        "html",
        "open",
        "lesson",
    ),
)
_CATALOG_INSTRUCTION: Final = (
    "Map the request to one route_id, run its first_command before custom work, "
    "never author new HTML when a route exists, then record the mapping with "
    "agent-tools route record --route-id <id> --profile-root <root> --json."
)


def has_weak_route_catalog_signal(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(signal.lower() in lowered for signal in WEAK_ROUTE_CATALOG_SIGNALS)


def build_route_catalog(
    repo_root: Path | None,
    profile: ProfileState | None,
) -> dict[str, JsonValue]:
    cards = [_builtin_wordbook_card()]
    if repo_root is not None:
        packs, _warnings = load_route_packs(repo_root, profile)
        cards.extend(
            {
                "route_id": pack.pack_id,
                "summary": pack.summary,
                "first_command": pack.first_command,
            }
            for pack in packs
        )
    return _budget_catalog(cards)


def _builtin_wordbook_card() -> dict[str, JsonValue]:
    return {
        "route_id": "lesson_wordbook_status",
        "summary": "Learner wordbook status/list side panel.",
        "first_command": (
            "side-panel wordbook open-plan --student <student> "
            "--profile-root <root> --json"
        ),
    }


def _budget_catalog(cards: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    if _catalog_size(cards) <= ROUTE_CATALOG_BYTE_CEILING:
        return {"instruction": _CATALOG_INSTRUCTION, "cards": [*cards]}
    kept: list[JsonValue] = []
    for card in cards:
        remaining_after_card = len(cards) - len(kept) - 1
        candidate: list[JsonValue] = [*kept, card]
        if remaining_after_card > 0:
            candidate.append(_truncation_marker(remaining_after_card))
        if _catalog_size(candidate) > ROUTE_CATALOG_BYTE_CEILING:
            break
        kept.append(card)
    omitted = len(cards) - len(kept)
    if omitted > 0:
        kept.append(_truncation_marker(omitted))
    return {"instruction": _CATALOG_INSTRUCTION, "cards": kept}


def _truncation_marker(omitted: int) -> dict[str, JsonValue]:
    return {
        "truncated": True,
        "omitted": omitted,
        "hint": "run agent-tools list --json or inspect route packs for more routes",
    }


def _catalog_size(cards: list[JsonValue] | list[dict[str, JsonValue]]) -> int:
    payload: dict[str, JsonValue] = {
        "instruction": _CATALOG_INSTRUCTION,
        "cards": [*cards],
    }
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
