from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from chat_lms_agent.agent_tools import REGISTRY_MANAGED_PATHS, parse_changed_files

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

ACADEMY_SCHEMA_PATH_PREFIX: Final = "src/chat_lms_agent/academy_db"
SIDE_PANEL_PATH_PREFIX: Final = "src/chat_lms_agent/side_panel"


@dataclass(frozen=True, slots=True)
class MemoryObligation:
    key: str
    scope: str
    text: str
    trigger: str


def obligations_for_changed_files(changed_files: tuple[str, ...]) -> tuple[MemoryObligation, ...]:
    obligations: set[MemoryObligation] = set()
    managed = set(REGISTRY_MANAGED_PATHS)
    for file_path in changed_files:
        normalized = file_path.replace("\\", "/")
        if normalized in managed:
            obligations.add(
                MemoryObligation(
                    key="tool:agent-tools",
                    scope="tool-registry",
                    text="Agent tool registry changed; update reusable tool memory.",
                    trigger=normalized,
                ),
            )
        if normalized.startswith(ACADEMY_SCHEMA_PATH_PREFIX):
            obligations.update(_academy_schema_obligations(normalized))
        if normalized.startswith(SIDE_PANEL_PATH_PREFIX):
            obligations.add(
                MemoryObligation(
                    key="panel:side-panel",
                    scope="side-panel",
                    text="Side-panel contract changed; record the panel operating rule.",
                    trigger=normalized,
                ),
            )
    return tuple(sorted(obligations, key=lambda item: item.key))


def obligations_for_reason(reason: str | None) -> tuple[MemoryObligation, ...]:
    match reason:
        case "academy-db-init":
            obligations = _academy_schema_obligations("academy-db-init")
            return tuple(sorted(obligations, key=lambda item: item.key))
        case "tool-change":
            return (
                MemoryObligation(
                    key="tool:agent-tools",
                    scope="tool-registry",
                    text="Agent tool lifecycle changed; update reusable tool memory.",
                    trigger="tool-change",
                ),
            )
        case str() | None:
            return ()


def obligations_from_inputs(
    changed_files_value: str | None,
    reason: str | None,
) -> tuple[MemoryObligation, ...]:
    combined = {*obligations_for_changed_files(parse_changed_files(changed_files_value))}
    combined.update(obligations_for_reason(reason))
    return tuple(sorted(combined, key=lambda item: item.key))


def obligation_to_memory_json(obligation: MemoryObligation) -> dict[str, JsonValue]:
    return {
        "key": obligation.key,
        "scope": obligation.scope,
        "text": obligation.text,
        "trigger": obligation.trigger,
    }


def obligation_to_draft_json(obligation: MemoryObligation) -> dict[str, JsonValue]:
    return obligation_to_memory_json(obligation)


def _academy_schema_obligations(trigger: str) -> set[MemoryObligation]:
    return {
        MemoryObligation(
            key="decision:academy-db-schema",
            scope="academy-db",
            text="Academy DB schema changed; record the design decision before closeout.",
            trigger=trigger,
        ),
        MemoryObligation(
            key="schema:academy-db",
            scope="academy-db",
            text="Academy DB schema state changed; record the current schema contract.",
            trigger=trigger,
        ),
    }
