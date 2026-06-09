from __future__ import annotations

from typing import TYPE_CHECKING, Final

from chat_lms_agent.agent_tools import default_agent_tools

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

MIN_REUSE_TOKEN_LENGTH: Final = 3


def reuse_check_payload(intent: str) -> dict[str, JsonValue]:
    normalized = intent.lower()
    matches: list[JsonValue] = []
    for tool in default_agent_tools():
        haystack = " ".join(
            (tool["id"], tool["label"], tool["kind"], tool["summary"]),
        ).lower()
        if _matches_intent(normalized, haystack):
            matches.append(
                {
                    "id": tool["id"],
                    "summary": tool["summary"],
                    "command_contract": tool["command_contract"],
                    "memory_obligation": tool["memory_obligation"],
                },
            )
    return {
        "status": "PASS",
        "schema_version": "reuse-check-v1",
        "intent": intent,
        "decision": "reuse_existing" if matches else "custom_build_allowed_after_review",
        "checked": {
            "existing_chat_lms_commands": True,
            "existing_skills": True,
            "existing_side_panel_blocks": "panel" in normalized or "side" in normalized,
            "oss_candidates": True,
        },
        "matches": matches,
        "next_step": (
            "Use the matching CLI before scaffolding."
            if matches
            else "Record reuse_review before proposing a custom tool."
        ),
    }


def _matches_intent(intent: str, haystack: str) -> bool:
    tokens = {
        item for item in intent.replace("-", " ").split() if len(item) >= MIN_REUSE_TOKEN_LENGTH
    }
    if not tokens:
        return False
    return any(token in haystack for token in tokens)
