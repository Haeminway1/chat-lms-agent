from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from chat_lms_agent.agent_tools import AgentTool, default_agent_tools
from chat_lms_agent.oss_references import OSS_REFERENCE_REGISTRY
from chat_lms_agent.side_panel import side_panel_contract_shape
from chat_lms_agent.skills import skills_payload

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

MIN_REUSE_TOKEN_LENGTH: Final = 3
SHORT_REUSE_TOKENS: Final = frozenset(("db", "qa", "ui", "단어", "패널", "현황", "보고", "조회"))
REUSE_TOKEN_ALIASES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "단어": ("wordbook", "vocabulary"),
        "단어장": ("wordbook", "vocabulary"),
        "패널": ("panel", "side-panel"),
        "현황": ("wordbook", "status"),
        "보고": ("wordbook", "report"),
        "조회": ("wordbook", "lookup"),
        "리스트": ("wordbook", "list"),
        "목록": ("wordbook", "list"),
        "열어줘": ("open", "open-plan"),
    },
)
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
        haystack = _tool_search_text(tool).lower()
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
    tokens = _reuse_tokens(intent)
    if not tokens:
        return False
    return any(token in haystack for token in tokens)


def _reuse_tokens(intent: str) -> set[str]:
    tokens: set[str] = set()
    for item in intent.replace("-", " ").split():
        if _is_reuse_token(item):
            tokens.add(item)
            tokens.update(REUSE_TOKEN_ALIASES.get(item, ()))
    return tokens


def _tool_search_text(tool: AgentTool) -> str:
    parts = (
        tool["id"],
        tool["label"],
        tool["kind"],
        tool["summary"],
        *_json_text_parts(tool["command_contract"]),
    )
    if tool["id"] == "side-panel":
        parts = (*parts, *_json_text_parts(side_panel_contract_shape()))
    return " ".join(parts)


def _json_text_parts(value: JsonValue) -> tuple[str, ...]:
    match value:
        case str():
            return (value,)
        case list():
            parts: list[str] = []
            for item in value:
                parts.extend(_json_text_parts(item))
            return tuple(parts)
        case dict():
            parts = []
            for item in value.values():
                parts.extend(_json_text_parts(item))
            return tuple(parts)
        case bool() | int() | float() | None:
            return ()


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
