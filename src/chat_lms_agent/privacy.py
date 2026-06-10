"""Two-mode learner-PII pseudonymization.

Structural reference: the oh-my-pi ``secrets.yml`` contract, inverted for
learner data. Reversible entries become deterministic placeholders that only
owner-facing surfaces may restore (a pure local lookup against a reverse map
that never leaves profile state); one-way entries are replaced and can never
round-trip. Applied after secret/path redaction on every model-bound text.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from chat_lms_agent.state import read_state_mapping, write_state_mapping

if TYPE_CHECKING:
    from chat_lms_agent.state import ProfileState

PRIVACY_FILE: Final = "privacy.json"
PRIVACY_REVERSE_FILE: Final = "privacy-reverse.json"
PRIVACY_SCHEMA_VERSION: Final = "privacy-v1"

type PrivacyMode = Literal["reversible", "oneway"]
type PrivacyKind = Literal["plain", "regex"]

_PLACEHOLDER_RE: Final = re.compile(r"\[P:[0-9a-f]{8}\]")


@dataclass(frozen=True, slots=True)
class PrivacyEntry:
    match: str
    kind: PrivacyKind
    mode: PrivacyMode
    replacement: str


def pseudonymize_text(profile: ProfileState, text: str) -> str:
    entries = _load_entries(profile)
    if not entries:
        return text
    result = text
    reverse_updates: dict[str, str] = {}
    for entry in entries:
        if entry.mode == "reversible":
            placeholder = _placeholder(entry.match)
            replaced = _apply(entry, result, placeholder)
            if replaced != result:
                reverse_updates[placeholder] = entry.match
            result = replaced
        else:
            result = _apply(entry, result, entry.replacement or "[비공개]")
    if reverse_updates:
        reverse_map = read_state_mapping(profile, PRIVACY_REVERSE_FILE)
        changed = False
        for placeholder, original in reverse_updates.items():
            if reverse_map.get(placeholder) != original:
                reverse_map[placeholder] = original
                changed = True
        if changed:
            write_state_mapping(profile, PRIVACY_REVERSE_FILE, reverse_map)
    return result


def restore_text(profile: ProfileState, text: str) -> str:
    """Owner-facing restore: a pure local lookup, never an inference."""
    if not _PLACEHOLDER_RE.search(text):
        return text
    reverse_map = read_state_mapping(profile, PRIVACY_REVERSE_FILE)

    def _restore(match: re.Match[str]) -> str:
        original = reverse_map.get(match.group(0))
        if isinstance(original, str):
            return original
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_restore, text)


def _apply(entry: PrivacyEntry, text: str, replacement: str) -> str:
    if entry.kind == "regex":
        try:
            return re.sub(entry.match, replacement.replace("\\", "\\\\"), text)
        except re.error:
            return text
    return text.replace(entry.match, replacement)


def _placeholder(match: str) -> str:
    digest = hashlib.sha256(match.encode("utf-8")).hexdigest()[:8]
    return f"[P:{digest}]"


def _load_entries(profile: ProfileState) -> list[PrivacyEntry]:
    payload = read_state_mapping(profile, PRIVACY_FILE)
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        return []
    entries: list[PrivacyEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        match = item.get("match")
        if not isinstance(match, str) or not match:
            continue
        kind = item.get("kind")
        mode = item.get("mode")
        replacement = item.get("replacement")
        entries.append(
            PrivacyEntry(
                match=match,
                kind="regex" if kind == "regex" else "plain",
                mode="oneway" if mode == "oneway" else "reversible",
                replacement=replacement if isinstance(replacement, str) else "",
            ),
        )
    return entries
