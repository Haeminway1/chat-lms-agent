from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Sequence

    from chat_lms_agent.hook_payloads import HookPayload
    from chat_lms_agent.state import JsonValue, ProfileState

from chat_lms_agent import __version__
from chat_lms_agent.academy_db_handlers import handle_academy_db
from chat_lms_agent.agent_tool_handlers import handle_agent_tools
from chat_lms_agent.agent_tools import (
    memory_update_required_payload,
    parse_changed_files,
    touches_agent_tool_registry,
)
from chat_lms_agent.approval_handlers import handle_approval
from chat_lms_agent.classcard_handlers import handle_classcard
from chat_lms_agent.cli_io import (
    argument_error,
    flag,
    option,
    profile_options,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.command_parser import APP_NAME, CliArgumentError, build_parser
from chat_lms_agent.context import build_host_context, build_prompt_delta_context
from chat_lms_agent.context_handlers import handle_context
from chat_lms_agent.doctor import build_doctor_report
from chat_lms_agent.goal_handlers import handle_goal
from chat_lms_agent.gws_handlers import handle_gws
from chat_lms_agent.harness_handlers import handle_harness
from chat_lms_agent.hook_payloads import (
    InvalidHookPayload,
    invalid_hook_payload_json,
    read_hook_payload,
)
from chat_lms_agent.journal import write_trace
from chat_lms_agent.kakao_handlers import handle_kakao
from chat_lms_agent.memory_handlers import handle_memory
from chat_lms_agent.onboarding import result_to_jsonable, validate_answers
from chat_lms_agent.pre_tool_gate import evaluate_tool_call
from chat_lms_agent.prompt_routes import resolve_prompt_route
from chat_lms_agent.self_qa import append_qa_record
from chat_lms_agent.session_closeout import (
    claim_compact_recovery,
    record_compact_event,
    write_stop_closeout,
)
from chat_lms_agent.session_handlers import handle_session
from chat_lms_agent.side_panel_handlers import handle_side_panel
from chat_lms_agent.skill_handlers import handle_skills
from chat_lms_agent.tool_handlers import handle_tool
from chat_lms_agent.trace_audit_handlers import handle_audit, handle_trace
from chat_lms_agent.usage_telemetry import record_surface_use


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not args or args in (["-h"], ["--help"]):
        parser.print_help(sys.stdout)
        return 0
    if args == ["--version"]:
        _ = sys.stdout.write(f"{APP_NAME} {__version__}\n")
        return 0
    try:
        _ = parser.parse_args(args)
    except CliArgumentError as error:
        return argument_error(error.message, wants_json="--json" in args)
    return _dispatch(args, parser)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dispatch(args: list[str], parser: argparse.ArgumentParser) -> int:
    handlers: dict[str, Callable[[list[str]], int]] = {
        "doctor": _doctor,
        "context": lambda route_args: handle_context(route_args, _repo_root()),
        "onboarding": _onboarding,
        "profile": _profile,
        "tool": lambda route_args: handle_tool(route_args, _repo_root()),
        "agent-tools": lambda route_args: handle_agent_tools(route_args, _repo_root()),
        "skills": lambda route_args: handle_skills(route_args, _repo_root()),
        "memory": lambda route_args: handle_memory(route_args, _repo_root()),
        "session": lambda route_args: handle_session(route_args, _repo_root()),
        "hook": _hook,
        "bootstrap": _bootstrap,
        "side-panel": lambda route_args: handle_side_panel(route_args, _repo_root()),
        "academy-db": lambda route_args: handle_academy_db(route_args, _repo_root()),
        "classcard": lambda route_args: handle_classcard(route_args, _repo_root()),
        "gws": lambda route_args: handle_gws(route_args, _repo_root()),
        "kakao": lambda route_args: handle_kakao(route_args, _repo_root()),
        "harness": lambda route_args: handle_harness(route_args, _repo_root()),
        "approval": lambda route_args: handle_approval(route_args, _repo_root()),
        "trace": lambda route_args: handle_trace(route_args, _repo_root()),
        "audit": lambda route_args: handle_audit(route_args, _repo_root()),
        "goal": lambda route_args: handle_goal(route_args, _repo_root()),
    }
    handler = handlers.get(args[0])
    if handler is None:
        parser.print_help(sys.stdout)
        return 0
    return handler(args)


def _doctor(args: list[str]) -> int:
    profile_root, profile = profile_options(args)
    report = build_doctor_report(_repo_root(), profile_root, profile)
    checks: list[JsonValue] = [
        {
            "id": check.id,
            "status": check.status,
            "message_ko": check.message_ko,
            "repair_action": check.repair_action,
            "safe_to_auto_repair": check.safe_to_auto_repair,
        }
        for check in report.checks
    ]
    needs_approval: list[JsonValue] = []
    needs_approval.extend(report.needs_approval)
    repair_failed: list[JsonValue] = []
    repair_failed.extend(report.repair_failed)
    report_payload: dict[str, JsonValue] = {
        "status": report.status,
        "exit_code": report.exit_code,
        "checks": checks,
        "needs_approval": needs_approval,
        "repair_failed": repair_failed,
    }
    write_json(report_payload)
    return report.exit_code


def _onboarding(args: list[str]) -> int:
    result = validate_answers(Path(required_option(args, "--answers")))
    payload = result_to_jsonable(result)
    write_json(
        {
            "status": payload["status"],
            "exit_code": payload["exit_code"],
            "message_ko": payload["message_ko"],
        },
    )
    return result.exit_code


def _profile(args: list[str]) -> int:
    profile = profile_state_or_error(args, _repo_root())
    if profile is None:
        return 4
    write_json(
        {
            "status": "PASS",
            "profile_root": "<profile-root>",
            "state_dir": "<profile-root>/.chat-lms-state",
        },
    )
    return 0


def _hook(args: list[str]) -> int:
    profile = profile_state_or_error(args, _repo_root())
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
    return _hook_emit_context(args, event, profile, payload)


def _hook_terminal_result(
    event: str,
    profile: ProfileState,
    payload: HookPayload,
) -> int | None:
    if event == "pre-tool-use":
        return _hook_pre_tool_use(profile, payload)
    if event == "post-compact":
        # The host rejects stdout on compact events; store a recovery marker
        # and stay silent (the next session-start or prompt-submit claims it).
        record_compact_event(profile)
        return 0
    if event == "stop":
        return write_stop_closeout(
            profile,
            payload.session_id,
            stop_hook_active=payload.stop_hook_active,
        )
    if event == "post-tool-use":
        # Obligation violations already returned above; a clean tool result
        # re-injects nothing (event tiering, gap-analysis P0-5).
        write_json({"status": "PASS"})
        return 0
    return None


def _hook_emit_context(
    args: list[str],
    event: str,
    profile: ProfileState,
    payload: HookPayload,
) -> int:
    if event == "user-prompt-submit":
        context = build_prompt_delta_context(profile, payload.prompt)
        if payload.prompt is not None:
            route = resolve_prompt_route(payload.prompt, _repo_root(), profile)
            if route is not None:
                context["prompt_route"] = route.route_context
                _ = record_surface_use(profile, f"route:{route.route_id}")
    else:
        profile_root, profile_name = profile_options(args)
        context = build_host_context(_repo_root(), profile_root, profile_name)
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


def _bootstrap(args: list[str]) -> int:
    command = subcommand(args)
    if command == "plan":
        actions: list[JsonValue] = ["doctor", "hooks", "profile", "full-hook-lifecycle"]
        write_json({"status": "PASS", "actions": actions})
        return 0
    if command == "apply":
        write_json({"status": "PASS", "applied": ["safe-runtime-wiring"]})
        return 0
    if command == "sync-runtime":
        write_json({"status": "PASS", "synced": ["hooks", "context", "doctor"]})
        return 0
    actions = ["doctor", "hooks", "profile"]
    write_json({"status": "PASS", "actions": actions})
    return 0
