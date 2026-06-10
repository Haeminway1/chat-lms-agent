"""Zero-token bilingual memory recall.

Structural reference: roach-pi ``extensions/workspace-memory/recall.ts`` —
local keyword scoring with strict byte budgets, no embeddings, no LLM calls.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from chat_lms_agent.state import MemoryPayload

RECALL_TOP_K: Final = 5
RECALL_BYTE_BUDGET: Final = 8_000

_KOREAN_TOKEN_RE: Final = re.compile(r"[가-힣]{2,}")
_ASCII_TOKEN_RE: Final = re.compile(r"[a-zA-Z]{3,}")
_STOPWORDS: Final = frozenset(
    (
        "알려줘",
        "해줘",
        "주세요",
        "있어",
        "대해",
        "오늘",
        "내일",
        "그리고",
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
    ),
)


def recall_memory(entries: list[MemoryPayload], prompt: str) -> list[MemoryPayload]:
    """Return the top-K entries matching the prompt, inside the byte budget."""
    tokens = _tokens(prompt)
    if not tokens:
        return []
    scored: list[tuple[int, MemoryPayload]] = []
    for entry in entries:
        haystack = f"{entry['key']} {entry['text']}".lower()
        score = sum(1 for token in tokens if token in haystack)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1]["key"]))
    selected: list[MemoryPayload] = []
    used = 0
    for _, entry in scored[:RECALL_TOP_K]:
        size = len(json.dumps(entry, ensure_ascii=False).encode("utf-8"))
        if used + size > RECALL_BYTE_BUDGET:
            break
        selected.append(entry)
        used += size
    return selected


def _tokens(prompt: str) -> set[str]:
    lowered = prompt.lower()
    tokens: set[str] = {match.group() for match in _KOREAN_TOKEN_RE.finditer(lowered)}
    tokens.update(match.group() for match in _ASCII_TOKEN_RE.finditer(lowered))
    return {token for token in tokens if token not in _STOPWORDS}
