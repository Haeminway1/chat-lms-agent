from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, TypedDict, cast

from chat_lms_agent.hosts import active_host

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

REGISTRY_VERSION: Final = "1"
REGISTRY_MEMORY_OBLIGATION: Final = (
    "Any reusable agent tool or registry change must update the durable tool memory "
    "contract before closeout."
)
TOOL_MEMORY_KEY_PATTERN: Final = "tool:<id>"
REGISTRY_MANAGED_PATHS: Final = (
    "src/chat_lms_agent/agent_tools.py",
    "src/chat_lms_agent/agent_tool_handlers.py",
    "docs/agent-tool-registry.md",
)
SIDE_PANEL_PAYLOAD_VALIDATE_PREFIX: Final = (
    "python -m chat_lms_agent side-panel payload validate --from"
)
SIDE_PANEL_PAYLOAD_VALIDATE_COMMAND: Final = (
    f"{SIDE_PANEL_PAYLOAD_VALIDATE_PREFIX} <payload.json> --json"
)


class AgentTool(TypedDict):
    id: str
    label: str
    kind: str
    status: str
    summary: str
    command_contract: dict[str, JsonValue]
    memory_obligation: str
    source: str


@dataclass(frozen=True, slots=True)
class ProposalValidation:
    proposal_id: str | None
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ToolSpec:
    tool_id: str
    label: str
    kind: str
    status: str
    summary: str
    commands: tuple[str, ...]
    memory_obligation: str


def _classcard_commands() -> tuple[str, ...]:
    base = "python -m chat_lms_agent classcard"
    return (
        f"{base} upload --student <name> --profile-root <root> --json",
        f"{base} upload --student <name> --execute --profile-root <root> --json",
        f"{base} recover --checkpoint <path> --execute --profile-root <root> --json",
        f"{base} verify --checkpoint <path> --class-url <ClassMain-url> --json",
        f"{base} login --username <id> --password <pw> --json",
        f"{base} direct-upload --checkpoint <path> --class-url <ClassMain-url> --json",
        f"{base} direct-repair-audio --set-id <id> --json",
        (
            f"{base} study import --student <name> --from <classcard-results.json|csv|tsv> "
            "--date <yyyy-mm-dd> --profile-root <root> --json"
        ),
        f"{base} study summary --student <name> --profile-root <root> --json",
        f"{base} study due --student <name> --profile-root <root> --json",
        f"{base} study live --student <name> --profile-root <root> --json",
    )


def _gws_commands() -> tuple[str, ...]:
    base = "python -m chat_lms_agent gws"
    send_suffix = "--approval-id <id> --profile-root <root> --json"
    return (
        f"{base} setup --json",
        f"{base} status --json",
        f"{base} client install --json",
        f"{base} calendar list --from <iso> --to <iso> --json",
        f"{base} calendar create-event --title <t> --start <iso> --end <iso> --json",
        f"{base} drive upload --file <path> --folder-name <name> --json",
        f"{base} sheets create --title <t> --from-tsv <path> --json",
        f"{base} sheets append --sheet-id <id> --range <A1-range> --from-tsv <path> --json",
        f"{base} sheets update --sheet-id <id> --range <A1-range> --from-tsv <path> --json",
        f"{base} sheets clear --sheet-id <id> --range <A1-range> --json",
        f"{base} sheets batch-update --sheet-id <id> --from-json <payload.json> --json",
        f"{base} sheets batch-clear --sheet-id <id> --from-json <payload.json> --json",
        f"{base} gmail send --to <addr> --subject <s> --body-file <path> {send_suffix}",
    )


def _write_action_commands() -> tuple[str, ...]:
    base = "python -m chat_lms_agent write-action"
    return (
        f"{base} list --profile-root <root> --json",
        f"{base} explain --id <template-id> --profile-root <root> --json",
        f"{base} plan --id <template-id> --from <payload.json> --profile-root <root> --json",
        f"{base} apply --id <template-id> --from <payload.json> --profile-root <root> --json",
        f"{base} roster --class-code <code> --profile-root <root> --json",
        f"{base} doctor --profile-root <root> --json",
    )


def _kakao_commands() -> tuple[str, ...]:
    base = "python -m chat_lms_agent kakao"
    send_suffix = "--approval-id <id> --profile-root <root> --json"
    return (
        f"{base} login --headed --profile-root <root> --json",
        f"{base} calibrate --profile-root <root> --json",
        f"{base} status --profile-root <root> --json",
        f"{base} send-friend --message <text> --group <name> {send_suffix}",
        f"{base} chats pull --profile-root <root> --json",
        f"{base} chats reply --contact <id> --message <text> {send_suffix}",
        f"{base} history --contact <id> --profile-root <root> --json",
        f"{base} summary --contact <id> --profile-root <root> --json",
    )


def _outbound_sync_commands() -> tuple[str, ...]:
    base = "python -m chat_lms_agent outbound"
    return (
        f"{base} ledger init --database <profile-db> --json",
        (
            f"{base} daily-management sync --database <profile-db> "
            "--source-key daily_management.2026_06 --date <yyyy-mm-dd> "
            "--out-dir <private-report-dir> --execute --json"
        ),
        (
            f"{base} daily-management journal-plan --database <profile-db> "
            "--source-key daily_management.2026_06 --from <yyyy-mm-dd> --to <yyyy-mm-dd> "
            "--current-values-json <bounded-live-values.json> --out-dir <private-report-dir> --json"
        ),
        f"{base} plan --database <profile-db> --from-json <outbound-items.json> --json",
        (
            f"{base} ledger record --database <profile-db> "
            "--from-json <write-or-verified-items.json> --status verified --json"
        ),
        (
            "python -m chat_lms_agent gws sheets batch-update --sheet-id <id> "
            "--from-json <batch_update_payload.json> --json"
        ),
    )


def default_agent_tools() -> tuple[AgentTool, ...]:
    return (
        _tool(
            _ToolSpec(
                tool_id="side-panel",
                label="Side Panel",
                kind="ui_building_block",
                status="active",
                summary=(
                    f"Create {active_host().runtime_label} auxiliary panel payloads, including "
                    "단어 HTML wordbook open plans."
                ),
                commands=(
                    "python -m chat_lms_agent agent-tools prompt-check --prompt <text> --json",
                    "python -m chat_lms_agent side-panel spec --json",
                    "python -m chat_lms_agent side-panel block list --json",
                    (
                        "python -m chat_lms_agent side-panel wordbook open-plan "
                        "--student <name> --profile-root <root> --json"
                    ),
                    (
                        "python -m chat_lms_agent side-panel wordbook ensure-server "
                        "--profile-root <root> --json"
                    ),
                    SIDE_PANEL_PAYLOAD_VALIDATE_COMMAND,
                ),
                memory_obligation="Record tool:side-panel when panel blocks or rules change.",
            ),
        ),
        _tool(
            _ToolSpec(
                tool_id="write-action",
                label="Write Action",
                kind="database_workflow",
                status="active",
                summary=(
                    "Approved template-driven DB-write workflow for profile-local academy "
                    "database writes."
                ),
                commands=_write_action_commands(),
                memory_obligation=(
                    "Record tool:write-action with registered templates before relying on a "
                    "DB-write workflow."
                ),
            ),
        ),
        _tool(
            _ToolSpec(
                tool_id="classcard",
                label="ClassCard Upload",
                kind="browser_automation",
                status="active",
                summary=(
                    "클래스카드(classcard.net) 단어 세트 자동 업로드 도구. 첫 사용 때만 크롬 "
                    "로그인 1회, 이후 영속 프로필로 헤드리스 자동 실행. Optional extra: "
                    "uv pip install chat-lms-agent[classcard] && playwright install chromium."
                ),
                commands=_classcard_commands(),
                memory_obligation=(
                    "Record tool:classcard with the ClassMain URL per student, the "
                    "credentials/profile location, and the study import/summary lookup "
                    "workflow, including live percentage lookup, before relying on the "
                    "ClassCard workflow."
                ),
            ),
        ),
        _tool(
            _ToolSpec(
                tool_id="gws",
                label="Google Workspace",
                kind="external_api",
                status="active",
                summary=(
                    "구글 워크스페이스 CLI: 캘린더 일정 조회/등록, 구글 시트 생성/추가, "
                    "드라이브 파일 업로드(단어시험지/시험지 자료), 지메일 발송(교사 승인 "
                    "필수). 브라우저 자동화로 대체하지 말 것. 최초 1회 gws setup 으로 "
                    "OAuth 동의."
                ),
                commands=_gws_commands(),
                memory_obligation=(
                    "Record tool:gws with setup state and frequently used folder/sheet "
                    "targets before relying on the Workspace workflow."
                ),
            ),
        ),
        _tool(
            _ToolSpec(
                tool_id="outbound-sync",
                label="Outbound Sync",
                kind="external_sync_workflow",
                status="active",
                summary=(
                    "Reusable Google Sheets outbound sync planning with deterministic cell "
                    "mapping, local ledger idempotency, duplicate prevention, and protected "
                    "existing-cell writes for teacher-facing sheets."
                ),
                commands=_outbound_sync_commands(),
                memory_obligation=(
                    "Record tool:outbound-sync with private source_key mappings, live-read "
                    "range, write payload path, ledger record path, and verification manifest "
                    "after each external sync."
                ),
            ),
        ),
        _tool(
            _ToolSpec(
                tool_id="kakao",
                label="Kakao Channel",
                kind="browser_automation",
                status="planned",
                summary=(
                    "KakaoTalk Channel admin automation for friends-only broadcasts and "
                    "1:1 chat follow-up. Uses one headed login, profile-local calibration, "
                    "paced browser automation, and teacher approval for every human-facing send."
                ),
                commands=_kakao_commands(),
                memory_obligation=(
                    "Record tool:kakao with channel setup, calibration freshness, free-quota "
                    "ceiling, and approved test recipient before relying on the workflow."
                ),
            ),
        ),
    )


def agent_tools_payload() -> dict[str, JsonValue]:
    tools: list[JsonValue] = [_tool_json(tool) for tool in default_agent_tools()]
    return {
        "status": "PASS",
        "registry_version": REGISTRY_VERSION,
        "source": "public_repo_default_registry",
        "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "tools": tools,
    }


def agent_tools_context() -> list[JsonValue]:
    return [
        {
            "id": tool["id"],
            "status": tool["status"],
            "summary": tool["summary"],
            "memory_obligation": tool["memory_obligation"],
        }
        for tool in default_agent_tools()
    ]


def tool_registry_context() -> dict[str, JsonValue]:
    return {
        "source": "public_repo_default_registry",
        "registry_version": REGISTRY_VERSION,
        "command": "python -m chat_lms_agent agent-tools list --json",
        "proposal_validation": (
            "python -m chat_lms_agent agent-tools validate --from <proposal.json> --json"
        ),
        "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "tool_count": len(default_agent_tools()),
    }


def memory_policy_context() -> dict[str, JsonValue]:
    return {
        "registry_memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "tool_memory_key_pattern": TOOL_MEMORY_KEY_PATTERN,
        "registry_change_rule": (
            "Reusable tool changes must include a command contract and a memory obligation."
        ),
        "public_private_boundary": (
            "The public repo stores tool contracts only; runtime memory remains in profile "
            ".chat-lms-state."
        ),
    }


def validate_agent_tool_proposal(path: Path) -> ProposalValidation:
    payload = _load_json_object(path)
    if payload is None:
        return ProposalValidation(proposal_id=None, errors=("INVALID_JSON",))

    errors: list[str] = []
    raw_id = payload.get("id")
    proposal_id = raw_id if isinstance(raw_id, str) else None
    if proposal_id is None:
        errors.append("MISSING_ID")
    if not _has_memory_obligation(payload.get("memory_obligation")):
        errors.append("MISSING_MEMORY_OBLIGATION")
    if not _has_command_contract(payload.get("command_contract")):
        errors.append("MISSING_COMMAND_CONTRACT")
    if not _non_empty_string(payload.get("summary")):
        errors.append("MISSING_SUMMARY")
    if not _has_reuse_review(payload.get("reuse_review")):
        errors.append("MISSING_REUSE_REVIEW")
    return ProposalValidation(proposal_id=proposal_id, errors=tuple(errors))


def validation_payload(result: ProposalValidation) -> dict[str, JsonValue]:
    if not result.errors:
        return {
            "status": "PASS",
            "proposal_id": result.proposal_id,
            "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        }
    return {
        "status": "ERROR",
        "error_code": "INVALID_TOOL_PROPOSAL",
        "proposal_id": result.proposal_id,
        "errors": list(result.errors),
    }


def parse_changed_files(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    normalized = value.replace(";", ",").replace("\n", ",")
    return tuple(item.strip().replace("\\", "/") for item in normalized.split(",") if item.strip())


def touches_agent_tool_registry(changed_files: tuple[str, ...]) -> bool:
    managed = set(REGISTRY_MANAGED_PATHS)
    return any(file_path in managed for file_path in changed_files)


def memory_update_required_payload(changed_files: tuple[str, ...]) -> dict[str, JsonValue]:
    return {
        "status": "BLOCKED",
        "error_code": "MEMORY_UPDATE_REQUIRED",
        "message": "agent tool registry changes require a durable memory update",
        "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "changed_files": list(changed_files),
    }


def _tool(spec: _ToolSpec) -> AgentTool:
    command_values: list[JsonValue] = list(spec.commands)
    command_contract: dict[str, JsonValue] = {
        "commands": command_values,
        "json_required": True,
        "public_safe": True,
    }
    return {
        "id": spec.tool_id,
        "label": spec.label,
        "kind": spec.kind,
        "status": spec.status,
        "summary": spec.summary,
        "command_contract": command_contract,
        "memory_obligation": spec.memory_obligation,
        "source": "public_repo_default_registry",
    }


def _tool_json(tool: AgentTool) -> dict[str, JsonValue]:
    return {
        "id": tool["id"],
        "label": tool["label"],
        "kind": tool["kind"],
        "status": tool["status"],
        "summary": tool["summary"],
        "command_contract": tool["command_contract"],
        "memory_obligation": tool["memory_obligation"],
        "source": tool["source"],
    }


def _load_json_object(path: Path) -> dict[str, JsonValue] | None:
    try:
        raw = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(raw, dict):
        return raw
    return None


def _has_memory_obligation(value: JsonValue | None) -> bool:
    if _non_empty_string(value):
        return True
    if not isinstance(value, dict):
        return False
    key = value.get("key")
    scope = value.get("scope")
    text = value.get("text")
    return _non_empty_string(key) and _non_empty_string(scope) and _non_empty_string(text)


def _has_command_contract(value: JsonValue | None) -> bool:
    if not isinstance(value, dict):
        return False
    command = value.get("command")
    commands = value.get("commands")
    if _non_empty_string(command):
        return True
    return isinstance(commands, list) and any(_non_empty_string(item) for item in commands)


def _has_reuse_review(value: JsonValue | None) -> bool:
    if not isinstance(value, dict):
        return False
    checked = value.get("checked_existing")
    justification = value.get("custom_build_justification")
    return isinstance(checked, list) and bool(checked) and _non_empty_string(justification)


def _non_empty_string(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
