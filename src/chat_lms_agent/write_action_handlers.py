"""CLI handlers for write-action templates."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent import classcard_db
from chat_lms_agent.cli_io import (
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.write_actions import (
    PlanError,
    WriteActionTemplate,
    WriteStep,
    compile_plan,
    load_write_actions,
    validate_template,
)
from chat_lms_agent.write_engine import ConnectFn, run_write_action

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from chat_lms_agent.state import JsonValue, ProfileState
    from chat_lms_agent.write_actions import CompiledPlan


EXIT_ERROR: Final = 2
EXIT_UNSAFE: Final = 4


def handle_write_action(
    args: list[str],
    repo_root: Path,
    *,
    connect: ConnectFn = classcard_db.connect,
) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return EXIT_UNSAFE
    command = subcommand(args)
    handlers: dict[str, Callable[[], int]] = {
        "list": lambda: _list(repo_root, profile),
        "explain": lambda: _explain(args, repo_root, profile),
        "plan": lambda: _plan(args, repo_root, profile),
        "apply": lambda: _apply(args, repo_root, profile, connect),
        "doctor": lambda: _doctor(repo_root, profile),
    }
    handler = handlers.get(command)
    if handler is None:
        write_json({"status": "ERROR", "error_code": "UNKNOWN_WRITE_ACTION_COMMAND"})
        return EXIT_ERROR
    return handler()


def _list(repo_root: Path, profile: ProfileState) -> int:
    templates, warnings = load_write_actions(repo_root, profile)
    write_json(
        {
            "status": "PASS",
            "templates": [_template_list_item(template) for template in templates],
            "warnings": list(warnings),
        },
    )
    return 0


def _explain(args: list[str], repo_root: Path, profile: ProfileState) -> int:
    template = _find_template(repo_root, profile, required_option(args, "--id"))
    if template is None:
        return _unknown_template()
    write_json(
        {
            "status": "PASS",
            "id": template.template_id,
            "summary": template.summary,
            "source": template.source,
            "route_id": template.route_id,
            "table_whitelist": _json_strings(template.table_whitelist),
            "columns": _columns_payload(template),
            "param_schema": _param_schema_payload(template),
            "steps": [_step_item(step) for step in template.steps],
        },
    )
    return 0


def _plan(args: list[str], repo_root: Path, profile: ProfileState) -> int:
    template = _find_template(repo_root, profile, required_option(args, "--id"))
    if template is None:
        return _unknown_template()
    params = _load_payload(Path(required_option(args, "--from")))
    if params is None:
        return _invalid_payload()
    plan = compile_plan(template, params)
    if isinstance(plan, PlanError):
        write_json(
            {
                "status": "ERROR",
                "error_code": plan.code,
                "errors": list(plan.errors),
            },
        )
        return EXIT_ERROR
    write_json(
        {
            "status": "PASS",
            "dry_run": True,
            "statement_count": len(plan.steps),
            "steps": _compiled_step_items(template, params, plan),
        },
    )
    return 0


def _apply(
    args: list[str],
    repo_root: Path,
    profile: ProfileState,
    connect: ConnectFn,
) -> int:
    template = _find_template(repo_root, profile, required_option(args, "--id"))
    if template is None:
        return _unknown_template()
    params = _load_payload(Path(required_option(args, "--from")))
    if params is None:
        return _invalid_payload()
    exit_code, payload = run_write_action(
        profile,
        template,
        params,
        db_path=profile.root / "data" / "chat_lms.db",
        connect=connect,
    )
    write_json(payload)
    return exit_code


def _doctor(repo_root: Path, profile: ProfileState) -> int:
    templates, warnings = load_write_actions(repo_root, profile)
    template_results: list[JsonValue] = []
    invalid_count = 0
    for template in templates:
        errors = validate_template(template)
        if errors:
            invalid_count += 1
        template_results.append(
            {
                "id": template.template_id,
                "source": template.source,
                "errors": _json_strings(errors),
            },
        )
    write_json(
        {
            "status": "PASS" if invalid_count == 0 else "ERROR",
            "template_count": len(templates),
            "valid_count": len(templates) - invalid_count,
            "invalid_count": invalid_count,
            "templates": template_results,
            "warnings": _json_strings(warnings),
        },
    )
    return 0 if invalid_count == 0 else EXIT_ERROR


def _find_template(
    repo_root: Path,
    profile: ProfileState,
    template_id: str,
) -> WriteActionTemplate | None:
    templates, _warnings = load_write_actions(repo_root, profile)
    for template in templates:
        if template.template_id == template_id:
            return template
    return None


def _load_payload(path: Path) -> dict[str, JsonValue] | None:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _compiled_step_items(
    template: WriteActionTemplate,
    params: dict[str, JsonValue],
    plan: CompiledPlan,
) -> list[JsonValue]:
    items = _expanded_step_items(template.steps, params)
    if len(items) == len(plan.steps):
        return items
    return [
        {
            "step_id": f"step_{index + 1}",
            "op": "unknown",
            "table": "",
            "predicted_write": _statement_writes(step.sql_text),
        }
        for index, step in enumerate(plan.steps)
    ]


def _expanded_step_items(
    steps: tuple[WriteStep, ...],
    params: dict[str, JsonValue],
) -> list[JsonValue]:
    items: list[JsonValue] = []
    for step in steps:
        fanout = _fanout_count((*step.match.values(), *step.set.values()), params)
        for _index in range(fanout):
            match step.op:
                case "resolve":
                    items.append(_compiled_item(step, predicted_write=False))
                case "insert" | "update_stub":
                    items.append(_compiled_item(step, predicted_write=True))
                case "ensure":
                    items.append(_compiled_item(step, predicted_write=True))
                    items.append(_compiled_item(step, predicted_write=False))
                case _:
                    items.append(_compiled_item(step, predicted_write=False))
    return items


def _fanout_count(bindings: tuple[str, ...], params: dict[str, JsonValue]) -> int:
    for binding in bindings:
        if not binding.startswith("$"):
            continue
        head = binding[1:].split(".", maxsplit=1)[0]
        if not head.endswith("[]"):
            continue
        raw = params.get(head[:-2])
        if isinstance(raw, list):
            return len(raw)
    return 1


def _compiled_item(step: WriteStep, *, predicted_write: bool) -> dict[str, JsonValue]:
    return {
        "step_id": step.step_id,
        "op": step.op,
        "table": step.table,
        "predicted_write": predicted_write,
    }


def _statement_writes(sql_text: str) -> bool:
    return not sql_text.startswith("SELECT ")


def _template_list_item(template: WriteActionTemplate) -> dict[str, JsonValue]:
    return {
        "id": template.template_id,
        "summary": template.summary,
        "source": template.source,
        "route_id": template.route_id,
    }


def _columns_payload(template: WriteActionTemplate) -> dict[str, JsonValue]:
    return {
        table: _json_strings(columns)
        for table, columns in template.columns.items()
    }


def _param_schema_payload(template: WriteActionTemplate) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {}
    for name, rule in template.param_schema.items():
        entry: dict[str, JsonValue] = dict(rule)
        payload[name] = entry
    return payload


def _json_strings(values: Iterable[str]) -> list[JsonValue]:
    items: list[JsonValue] = []
    items.extend(values)
    return items


def _step_item(step: WriteStep) -> dict[str, JsonValue]:
    return {"step_id": step.step_id, "op": step.op, "table": step.table}


def _unknown_template() -> int:
    write_json({"status": "ERROR", "error_code": "UNKNOWN_TEMPLATE"})
    return EXIT_ERROR


def _invalid_payload() -> int:
    write_json({"status": "ERROR", "error_code": "INVALID_PAYLOAD"})
    return EXIT_ERROR
