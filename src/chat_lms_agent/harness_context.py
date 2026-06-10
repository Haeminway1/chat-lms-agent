from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.academy_db import SCHEMA_VERSION, store_path

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

HOOK_EVENTS: Final = (
    "PostCompact",
    "PostToolUse",
    "PreToolUse",
    "SessionStart",
    "Stop",
    "UserPromptSubmit",
)


def hook_lifecycle_context(repo_root: Path) -> dict[str, JsonValue]:
    return {
        "registered_events": _registered_hook_events(repo_root),
        "payload_source": "stdin-json",
        "command": "python -m chat_lms_agent hook <event> --json",
        "malformed_payload_error": "INVALID_HOOK_PAYLOAD",
    }


def memory_obligations_context() -> dict[str, JsonValue]:
    return {
        "command": "python -m chat_lms_agent memory verify --changed-files <paths> --json",
        "draft_command": "python -m chat_lms_agent memory draft --for <reason> --json",
        "apply_command": "python -m chat_lms_agent memory apply-draft --from <draft.json> --json",
        "keys": [
            "tool:<id>",
            "db:<id>",
            "schema:<id>",
            "query:<id>",
            "panel:<view>",
            "decision:<topic>",
        ],
    }


def tool_lifecycle_context() -> dict[str, JsonValue]:
    return {
        "commands": [
            "agent-tools scaffold",
            "agent-tools register",
            "agent-tools promote",
            "agent-tools deprecate",
            "agent-tools explain",
            "agent-tools doctor",
        ],
        "required_contracts": [
            "command_contract",
            "memory_obligation",
            "safety_boundary",
            "test_contract",
        ],
    }


def academy_db_context(profile: ProfileState | None) -> dict[str, JsonValue]:
    initialized = profile is not None and store_path(profile).exists()
    return {
        "schema_version": SCHEMA_VERSION,
        "initialized": initialized,
        "store": "<profile-root>/.chat-lms-state/academy/academy-store.json",
        "schema": {"entities": ["classes", "learners", "lessons"]},
        "query_inventory": ["learner-count", "class-count"],
        "commands": [
            "academy-db spec",
            "academy-db init",
            "academy-db inspect",
            "academy-db schema show",
            "academy-db query list",
            "academy-db query run",
            "academy-db import plan",
            "academy-db import apply",
        ],
    }


def _registered_hook_events(repo_root: Path) -> list[JsonValue]:
    hooks_path = repo_root / "hooks" / "hooks.json"
    try:
        payload = cast("JsonValue", json.loads(hooks_path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return []
    if not isinstance(payload, dict):
        return []
    registered = sorted(event for event in HOOK_EVENTS if event in payload)
    return list(registered)
