from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

from chat_lms_agent.agent_tools import (
    memory_update_required_payload,
    parse_changed_files,
    touches_agent_tool_registry,
)
from chat_lms_agent.cli_io import (
    flag,
    option,
    profile_options,
    profile_state_or_error,
    subcommand,
    write_json,
)
from chat_lms_agent.context import build_host_context, build_prompt_delta_context
from chat_lms_agent.hook_payloads import (
    InvalidHookPayload,
    invalid_hook_payload_json,
    read_hook_payload,
)
from chat_lms_agent.journal import write_trace
from chat_lms_agent.pre_tool_gate import evaluate_tool_call
from chat_lms_agent.prompt_route_catalog import (
    build_route_catalog,
    has_weak_route_catalog_signal,
)
from chat_lms_agent.prompt_routes import resolve_prompt_route
from chat_lms_agent.self_qa import append_qa_record
from chat_lms_agent.session_closeout import (
    claim_compact_recovery,
    record_compact_event,
    write_stop_closeout,
)
from chat_lms_agent.usage_telemetry import record_surface_use

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.hook_payloads import HookPayload
    from chat_lms_agent.state import JsonValue, ProfileState


def handle_hook(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    event = subcommand(args)
    payload = read_hook_payload(sys.stdin, event_name=event)
    if isinstance(payload, InvalidHookPayload):
        _ = append_qa_record(
            profile,
            "hook_anomaly",
            error_code=payload.error_code,
            summary=payload.message,
        )
        write_json(invalid_hook_payload_json(payload))
        return 2
    cli_changed_files = parse_changed_files(option(args, "--changed-files"))
    changed_files = (*cli_changed_files, *payload.changed_files)
    if (
        event in {"post-tool-use", "stop"}
        and touches_agent_tool_registry(changed_files)
        and not flag(args, "--memory-updated")
    ):
        write_json(memory_update_required_payload(changed_files))
        return 5
    terminal = _hook_terminal_result(event, profile, payload)
    if terminal is not None:
        return terminal
    return _hook_emit_context(args, event, profile, payload, repo_root)


def _hook_terminal_result(
    event: str,
    profile: ProfileState,
    payload: HookPayload,
) -> int | None:
    if event == "pre-tool-use":
        return _hook_pre_tool_use(profile, payload)
    if event == "post-compact":
        record_compact_event(profile)
        return 0
    if event == "stop":
        return write_stop_closeout(
            profile,
            payload.session_id,
            stop_hook_active=payload.stop_hook_active,
        )
    if event == "post-tool-use":
        write_json({"status": "PASS"})
        return 0
    return None


def _hook_emit_context(
    args: list[str],
    event: str,
    profile: ProfileState,
    payload: HookPayload,
    repo_root: Path,
) -> int:
    if event == "user-prompt-submit":
        context = build_prompt_delta_context(profile, payload.prompt)
        if payload.prompt is not None:
            route = resolve_prompt_route(payload.prompt, repo_root, profile)
            if route is not None:
                context["prompt_route"] = route.route_context
                _ = record_surface_use(profile, f"route:{route.route_id}")
            elif has_weak_route_catalog_signal(payload.prompt):
                context["route_catalog"] = build_route_catalog(repo_root, profile)
    else:
        profile_root, profile_name = profile_options(args)
        context = build_host_context(repo_root, profile_root, profile_name)
    recovery = claim_compact_recovery(profile, payload.source)
    if recovery is not None:
        context["compact_recovery"] = recovery
    write_json(
        {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": json.dumps(context, ensure_ascii=False, sort_keys=True),
            },
        },
    )
    return 0


def _hook_pre_tool_use(profile: ProfileState, payload: HookPayload) -> int:
    decision = evaluate_tool_call(profile, payload.tool_name, payload.tool_input)
    if decision.permission == "deny":
        _ = write_trace(
            profile,
            "pre_tool_use_denied",
            f"PreToolUse denied by {decision.rule_id}",
            details={
                "rule_id": decision.rule_id,
                "tool_name": payload.tool_name or "",
                "tier": decision.tier,
            },
        )
        write_json(
            {
                "status": "BLOCKED",
                "permissionDecision": "deny",
                "error_code": decision.rule_id,
                "reason": decision.reason_ko,
            },
        )
        return 5
    response: dict[str, JsonValue] = {
        "status": "PASS",
        "permissionDecision": decision.permission,
    }
    if decision.reason_ko is not None:
        response["reason"] = decision.reason_ko
    write_json(response)
    return 0
