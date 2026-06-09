from __future__ import annotations

from typing import TYPE_CHECKING, Final

from chat_lms_agent.agent_tools import AgentTool, default_agent_tools
from chat_lms_agent.oss_references import OSS_REFERENCE_REGISTRY
from chat_lms_agent.skills import skills_payload

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

MIN_REUSE_TOKEN_LENGTH: Final = 3
SHORT_REUSE_TOKENS: Final = frozenset(("db", "qa", "ui"))
REUSE_STOPWORDS: Final = frozenset(
    (
        "add",
        "build",
        "create",
        "make",
        "new",
        "run",
        "use",
        "using",
    ),
)


def reuse_check_payload(intent: str, repo_root: Path | None = None) -> dict[str, JsonValue]:
    normalized = intent.lower()
    matches: list[JsonValue] = []
    tools = default_agent_tools()
    for tool in tools:
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
    skill_count = _skill_count(repo_root)
    command_count = sum(_command_count(tool) for tool in tools)
    return {
        "status": "PASS",
        "schema_version": "reuse-check-v1",
        "intent": intent,
        "decision": "reuse_existing" if matches else "custom_build_allowed_after_review",
        "checked": {
            "existing_chat_lms_commands": command_count > 0,
            "existing_skills": skill_count > 0,
            "existing_side_panel_blocks": any(tool["id"] == "side-panel" for tool in tools),
            "oss_candidates": bool(OSS_REFERENCE_REGISTRY),
            "agent_tool_count": len(tools),
            "chat_lms_command_count": command_count,
            "skill_count": skill_count,
            "oss_candidate_count": len(OSS_REFERENCE_REGISTRY),
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
        item
        for item in intent.replace("-", " ").split()
        if _is_reuse_token(item)
    }
    if not tokens:
        return False
    return any(token in haystack for token in tokens)


def _is_reuse_token(value: str) -> bool:
    if value in REUSE_STOPWORDS:
        return False
    return len(value) >= MIN_REUSE_TOKEN_LENGTH or value in SHORT_REUSE_TOKENS


def _skill_count(repo_root: Path | None) -> int:
    if repo_root is None:
        return 0
    skills = skills_payload(repo_root).get("skills")
    if not isinstance(skills, list):
        return 0
    return len(skills)


def _command_count(tool: AgentTool) -> int:
    command_items = tool["command_contract"].get("commands")
    if not isinstance(command_items, list):
        return 0
    return len(command_items)
