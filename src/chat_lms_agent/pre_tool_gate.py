"""PreToolUse safety gate: a pure tier/policy/override decision table.

Structural reference: the approval-tier algebra in oh-my-pi
(``tools/approval.ts``), with defaults inverted for this harness — unknown
tool classes resolve to a teacher prompt (``ask``), never to silent allow,
and ledgers under the runtime state directory are runtime-owned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from chat_lms_agent.approvals import has_unconsumed_approved
from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

type GateTier = Literal["read", "write", "exec"]
type GatePermission = Literal["allow", "ask", "deny"]

READ_TOOLS: Final = frozenset({"read", "glob", "grep", "list", "ls", "view", "search"})
WRITE_TOOLS: Final = frozenset({"write", "edit", "apply_patch", "notebookedit", "multiedit"})
EXEC_TOOLS: Final = frozenset({"bash", "shell", "powershell", "exec_command", "terminal"})

_DESTRUCTIVE_PATTERNS: Final = (
    re.compile(r"remove-item\s+(?:-\w+\s+)*-recurse", re.IGNORECASE),
    re.compile(r"\bdel\s+/s\b", re.IGNORECASE),
    re.compile(r"\bformat(?:\.com)?\s+[a-z]:", re.IGNORECASE),
    re.compile(r"\breg\s+delete\b", re.IGNORECASE),
    re.compile(r"\bgit\s+push\s+--force\b", re.IGNORECASE),
    re.compile(r"\brm\s+-rf?\b", re.IGNORECASE),
    re.compile(r"\brmdir\s+/s\b", re.IGNORECASE),
)
_WRITE_REDIRECT_PATTERNS: Final = (
    re.compile(r"set-content|out-file|add-content", re.IGNORECASE),
    re.compile(r">{1,2}"),
)
_PRIVATE_DATA_MARKERS: Final = (
    STATE_DIR,
    "data/academy",
    "data\\academy",
    "academy-store",
    "memory.json",
    "approvals.json",
    "backups",
)
_CONTENT_KEYS: Final = ("content", "new_string", "text", "body")


@dataclass(frozen=True, slots=True)
class GateDecision:
    permission: GatePermission
    tier: GateTier
    rule_id: str | None = None
    reason_ko: str | None = None


def evaluate_tool_call(
    profile: ProfileState,
    tool_name: str | None,
    tool_input: JsonValue | None,
) -> GateDecision:
    tier = _classify_tier(tool_name)
    if tier is None:
        return GateDecision(
            permission="ask",
            tier="exec",
            rule_id="UNKNOWN_TOOL_CLASS",
            reason_ko="알 수 없는 도구 호출입니다. 교사 확인 후 진행하세요.",
        )
    if tier == "read":
        return GateDecision(permission="allow", tier="read")
    text = _flatten_text(tool_input)
    file_path = _first_input_string(tool_input, ("file_path", "filePath", "path"))
    state_decision = _runtime_owned_state_decision(tier, file_path, text)
    if state_decision is not None:
        return state_decision
    if tier == "write":
        boundary = _public_write_decision(profile, file_path, tool_input)
        if boundary is not None:
            return boundary
        return GateDecision(permission="allow", tier="write")
    return _exec_decision(profile, text)


def _runtime_owned_state_decision(
    tier: GateTier,
    file_path: str | None,
    text: str,
) -> GateDecision | None:
    reason = (
        "런타임 원장은 에이전트가 직접 수정할 수 없습니다. "
        "python -m chat_lms_agent CLI 명령으로만 변경하세요."
    )
    if tier == "write" and file_path is not None and STATE_DIR in file_path:
        return GateDecision("deny", tier, "RUNTIME_OWNED_STATE", reason)
    if tier == "exec" and STATE_DIR in text and _mutates(text):
        return GateDecision("deny", tier, "RUNTIME_OWNED_STATE", reason)
    return None


def _public_write_decision(
    profile: ProfileState,
    file_path: str | None,
    tool_input: JsonValue | None,
) -> GateDecision | None:
    if file_path is None or not isinstance(tool_input, dict):
        return None
    target = Path(file_path)
    if not target.is_absolute():
        target = profile.repo_root / target
    try:
        _ = target.resolve().relative_to(profile.repo_root.resolve())
    except ValueError:
        return None
    content = " ".join(
        value
        for key in _CONTENT_KEYS
        if isinstance(value := tool_input.get(key), str)
    )
    if STATE_DIR in content or str(profile.root) in content:
        return GateDecision(
            permission="deny",
            tier="write",
            rule_id="PRIVATE_REFERENCE_IN_PUBLIC_WRITE",
            reason_ko=(
                "사설 프로필 정보를 공개 레포 파일에 쓸 수 없습니다. "
                "레닥션된 요약만 공개 문서에 기록하세요."
            ),
        )
    return None


def _exec_decision(profile: ProfileState, text: str) -> GateDecision:
    if _is_destructive(text) and _touches_private_data(text):
        if has_unconsumed_approved(profile):
            return GateDecision(
                permission="allow",
                tier="exec",
                rule_id="DESTRUCTIVE_WITH_APPROVAL",
            )
        return GateDecision(
            permission="deny",
            tier="exec",
            rule_id="DESTRUCTIVE_WITHOUT_APPROVAL",
            reason_ko=(
                "사설 데이터에 대한 파괴적 명령은 교사 승인이 필요합니다. "
                "approval 원장에 승인된 항목이 있어야 실행할 수 있습니다."
            ),
        )
    return GateDecision(permission="allow", tier="exec")


def _classify_tier(tool_name: str | None) -> GateTier | None:
    if tool_name is None:
        return None
    normalized = tool_name.strip().lower()
    if normalized in READ_TOOLS:
        return "read"
    if normalized in WRITE_TOOLS:
        return "write"
    if normalized in EXEC_TOOLS:
        return "exec"
    return None


def _is_destructive(text: str) -> bool:
    return any(pattern.search(text) for pattern in _DESTRUCTIVE_PATTERNS)


def _mutates(text: str) -> bool:
    if _is_destructive(text):
        return True
    return any(pattern.search(text) for pattern in _WRITE_REDIRECT_PATTERNS)


def _touches_private_data(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in _PRIVATE_DATA_MARKERS)


def _first_input_string(tool_input: JsonValue | None, keys: tuple[str, ...]) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _flatten_text(value: JsonValue | None) -> str:
    parts: list[str] = []
    _collect_text(value, parts)
    return " ".join(parts)


def _collect_text(value: JsonValue | None, parts: list[str]) -> None:
    match value:
        case str() as item:
            parts.append(item)
        case list() as values:
            for item in values:
                _collect_text(item, parts)
        case dict() as mapping:
            for item in mapping.values():
                _collect_text(item, parts)
        case bool() | int() | float() | None:
            return
