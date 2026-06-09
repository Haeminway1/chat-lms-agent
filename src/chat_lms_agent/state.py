from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Final, Literal, TypedDict, cast

ToolStatus = Literal["draft", "active", "deprecated"]
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

STATE_DIR: Final = ".chat-lms-state"
TOOLS_FILE: Final = "tools.json"
MEMORY_FILE: Final = "memory.json"


class ToolPayload(TypedDict):
    name: str
    kind: str
    summary: str
    command: str | None
    template: str | None
    status: ToolStatus


class MemoryPayload(TypedDict):
    key: str
    scope: str
    text: str


@dataclass(frozen=True, slots=True)
class ProfileState:
    root: Path
    repo_root: Path


def resolve_profile_state(
    repo_root: Path,
    profile_root: str | None,
    profile: str | None,
) -> ProfileState | str:
    if profile is not None:
        return ProfileState(
            root=repo_root / "tests" / "fixtures" / "profiles" / profile,
            repo_root=repo_root,
        )
    if profile_root is None:
        root = _empty_runtime_root()
        if _is_under_repo(root, repo_root):
            return "PUBLIC_REPO_STATE_REJECTED"
        return ProfileState(root=root, repo_root=repo_root)

    root = Path(profile_root)
    if not root.is_absolute():
        root = repo_root / root
    resolved_root = root.resolve()
    if _is_under_repo(resolved_root, repo_root):
        return "PUBLIC_REPO_STATE_REJECTED"
    return ProfileState(root=resolved_root, repo_root=repo_root)


def load_tools(profile: ProfileState) -> list[ToolPayload]:
    payload = _read_json_mapping(_state_dir(profile) / TOOLS_FILE)
    raw_tools = payload.get("tools", [])
    if not isinstance(raw_tools, list):
        return []

    tools: list[ToolPayload] = []
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        tool = _parse_tool(item)
        if tool is not None:
            tools.append(tool)
    return sorted(tools, key=lambda tool: tool["name"])


def save_tools(profile: ProfileState, tools: list[ToolPayload]) -> None:
    _write_json(_state_dir(profile) / TOOLS_FILE, {"tools": tools})


def load_memory(profile: ProfileState) -> list[MemoryPayload]:
    payload = _read_json_mapping(_state_dir(profile) / MEMORY_FILE)
    raw_memory = payload.get("memory", [])
    if not isinstance(raw_memory, list):
        return []

    entries: list[MemoryPayload] = []
    for item in raw_memory:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        scope = item.get("scope")
        text = item.get("text")
        if isinstance(key, str) and isinstance(scope, str) and isinstance(text, str):
            entries.append({"key": key, "scope": scope, "text": redact_text(text)})
    return sorted(entries, key=lambda entry: entry["key"])


def save_memory(profile: ProfileState, entries: list[MemoryPayload]) -> None:
    _write_json(_state_dir(profile) / MEMORY_FILE, {"memory": entries})


def redact_text(value: str) -> str:
    patterns = (
        re.compile(r"[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD)[A-Z0-9_]*=[^\s,;]+"),
        re.compile(r"\b[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\b"),
        re.compile(r"(?i)\b(?:secret|token|password)\s*[=:]\s*[^\s,;]+"),
        re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|,;]+"),
        re.compile(r"/(?:Users|home|tmp|var/tmp|private/tmp|var/folders)/[^\s\"'<>|,;]+"),
    )
    redacted = value
    for pattern in patterns:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _state_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR


def _empty_runtime_root() -> Path:
    configured = os.environ.get("CHAT_LMS_AGENT_PROFILE_ROOT")
    if configured is not None:
        return Path(configured).resolve()
    return (Path(tempfile.gettempdir()) / "chat-lms-agent-empty-profile").resolve()


def _is_under_repo(path: Path, repo_root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_repo = repo_root.resolve()
    return resolved_path == resolved_repo or resolved_repo in resolved_path.parents


def _read_json_mapping(path: Path) -> dict[str, JsonValue]:
    if not path.exists():
        return {}
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _write_json(path: Path, payload: dict[str, list[ToolPayload] | list[MemoryPayload]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _parse_tool(item: dict[str, JsonValue]) -> ToolPayload | None:
    name = item.get("name")
    kind = item.get("kind")
    summary = item.get("summary")
    status = _parse_tool_status(item.get("status"))
    if not (
        isinstance(name, str)
        and isinstance(kind, str)
        and isinstance(summary, str)
        and status is not None
    ):
        return None
    command = item.get("command")
    template = item.get("template")
    return {
        "name": name,
        "kind": kind,
        "summary": redact_text(summary),
        "command": redact_text(command) if isinstance(command, str) else None,
        "template": redact_text(template) if isinstance(template, str) else None,
        "status": status,
    }


def _parse_tool_status(value: JsonValue | None) -> ToolStatus | None:
    match value:
        case "draft":
            return "draft"
        case "active":
            return "active"
        case "deprecated":
            return "deprecated"
        case _:
            return None
