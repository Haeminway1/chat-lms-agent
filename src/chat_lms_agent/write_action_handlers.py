"""CLI handlers for write-action templates."""

from __future__ import annotations

import json
import sqlite3
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent import approvals, classcard_db
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
EXIT_NEEDS_APPROVAL: Final = 3
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
        "register": lambda: _register(args, repo_root, profile),
        "plan": lambda: _plan(args, repo_root, profile),
        "apply": lambda: _apply(args, repo_root, profile, connect),
        "roster": lambda: _roster(args, profile),
        "session-gaps": lambda: _session_gaps(args, profile),
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


def _register(args: list[str], repo_root: Path, profile: ProfileState) -> int:
    template_id = required_option(args, "--id")
    template = _find_template(repo_root, profile, template_id)
    if template is None:
        return _unknown_template()
    plan_id = _registration_plan_id(template.template_id)
    approval_id = approvals.approval_id_for(plan_id)
    if approvals.approval_is_approved(profile, approval_id, plan_id):
        write_json(
            {
                "status": "PASS",
                "already_registered": True,
                "template_id": template.template_id,
            },
        )
        return 0
    request = approvals.ensure_approval_request(
        profile,
        plan_id=plan_id,
        operation="write-action register",
    )
    write_json(
        {
            "status": "NEEDS_APPROVAL",
            "approval_id": request["approval_id"],
            "plan_id": plan_id,
            "template_id": template.template_id,
            "hint": _register_approval_hint(request["approval_id"]),
        },
    )
    return EXIT_NEEDS_APPROVAL


def _apply(
    args: list[str],
    repo_root: Path,
    profile: ProfileState,
    connect: ConnectFn,
) -> int:
    template_id = required_option(args, "--id")
    template = _find_template(repo_root, profile, template_id)
    if template is None:
        return _unknown_template()
    plan_id = _registration_plan_id(template.template_id)
    approval_id = approvals.approval_id_for(plan_id)
    if not approvals.approval_is_approved(profile, approval_id, plan_id):
        write_json(
            {
                "status": "NEEDS_APPROVAL",
                "error_code": "TEMPLATE_NOT_REGISTERED",
                "template_id": template.template_id,
                "hint": _unregistered_apply_hint(approval_id),
            },
        )
        return EXIT_NEEDS_APPROVAL
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


def _roster(args: list[str], profile: ProfileState) -> int:
    db_path = profile.root / "data" / "chat_lms.db"
    try:
        with _connect_readonly(db_path) as conn:
            class_code = required_option(args, "--class-code")
            session_date = _optional_option(args, "--session-date")
            class_row = cast(
                "sqlite3.Row | None",
                conn.execute(
                    "SELECT id FROM classes WHERE code = ?",
                    (class_code,),
                ).fetchone(),
            )
            if class_row is None:
                write_json({"status": "ERROR", "error_code": "UNKNOWN_CLASS"})
                return EXIT_ERROR
            class_id = _row_int(class_row, "id")
            rows = cast(
                "list[sqlite3.Row]",
                conn.execute(
                    _active_enrollees_sql(
                        """
                        SELECT DISTINCT s.canonical_name, s.id
                        FROM classes c
                        JOIN enrollments e ON e.class_id = c.id
                        JOIN students s ON s.id = e.student_id
                        WHERE c.code = ?
                        """,
                        session_date=session_date,
                        order_by="ORDER BY s.id",
                    ),
                    _active_enrollees_params((class_code,), session_date=session_date),
                ).fetchall(),
            )
    except sqlite3.Error:
        write_json({"status": "ERROR", "error_code": "DB_UNAVAILABLE"})
        return EXIT_ERROR
    write_json(
        {
            "status": "PASS",
            "class_id": class_id,
            "students": [
                {"canonical_name": _row_str(row, "canonical_name"), "id": _row_int(row, "id")}
                for row in rows
            ],
        },
    )
    return 0


def _session_gaps(args: list[str], profile: ProfileState) -> int:
    db_path = profile.root / "data" / "chat_lms.db"
    try:
        with _connect_readonly(db_path) as conn:
            class_code = required_option(args, "--class-code")
            session_date = required_option(args, "--session-date")
            class_row = cast(
                "sqlite3.Row | None",
                conn.execute(
                    "SELECT id FROM classes WHERE code = ?",
                    (class_code,),
                ).fetchone(),
            )
            if class_row is None:
                write_json({"status": "ERROR", "error_code": "UNKNOWN_CLASS"})
                return EXIT_ERROR
            class_id = _row_int(class_row, "id")
            session_row = cast(
                "sqlite3.Row | None",
                conn.execute(
                    """
                    SELECT id
                    FROM sessions
                    WHERE class_id = ? AND session_date = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (class_id, session_date),
                ).fetchone(),
            )
            if session_row is None:
                write_json(
                    {
                        "status": "PASS",
                        "session_id": None,
                        "session_exists": False,
                        "missing": [],
                        "note": "no session for that date",
                    },
                )
                return 0
            session_id = _row_int(session_row, "id")
            total_enrolled = _active_enrollee_count(conn, class_id, session_date)
            recorded = _recorded_attendance_count(conn, session_id, class_id, session_date)
            missing_rows = cast(
                "list[sqlite3.Row]",
                conn.execute(
                    _active_enrollees_sql(
                        """
                    SELECT DISTINCT e.student_id
                    FROM enrollments e
                    LEFT JOIN student_session_records r
                      ON r.session_id = ? AND r.student_id = e.student_id
                    JOIN students s ON s.id = e.student_id
                    WHERE e.class_id = ?
                      AND r.attendance IS NULL
                    """,
                        session_date=session_date,
                        order_by="ORDER BY e.student_id",
                    ),
                    _active_enrollees_params((session_id, class_id), session_date=session_date),
                ).fetchall(),
            )
    except sqlite3.Error:
        write_json({"status": "ERROR", "error_code": "DB_UNAVAILABLE"})
        return EXIT_ERROR
    write_json(
        {
            "status": "PASS",
            "session_id": session_id,
            "session_exists": True,
            "total_enrolled": total_enrolled,
            "recorded": recorded,
            "missing": [{"student_id": _row_int(row, "student_id")} for row in missing_rows],
        },
    )
    return 0


def _active_enrollee_count(conn: sqlite3.Connection, class_id: int, session_date: str) -> int:
    row = cast(
        "sqlite3.Row",
        conn.execute(
            _active_enrollees_sql(
                """
            SELECT COUNT(DISTINCT e.student_id) AS total
            FROM enrollments e
            JOIN students s ON s.id = e.student_id
            WHERE e.class_id = ?
            """,
                session_date=session_date,
            ),
            _active_enrollees_params((class_id,), session_date=session_date),
        ).fetchone(),
    )
    return _row_int(row, "total")


def _recorded_attendance_count(
    conn: sqlite3.Connection,
    session_id: int,
    class_id: int,
    session_date: str,
) -> int:
    row = cast(
        "sqlite3.Row",
        conn.execute(
            _active_enrollees_sql(
                """
            SELECT COUNT(DISTINCT r.student_id) AS recorded
            FROM student_session_records r
            JOIN enrollments e ON e.student_id = r.student_id
            JOIN students s ON s.id = e.student_id
            WHERE r.session_id = ?
              AND e.class_id = ?
              AND r.attendance IS NOT NULL
            """,
                session_date=session_date,
            ),
            _active_enrollees_params((session_id, class_id), session_date=session_date),
        ).fetchone(),
    )
    return _row_int(row, "recorded")


def _active_enrollees_sql(base_sql: str, *, session_date: str | None, order_by: str = "") -> str:
    date_filter = ""
    if session_date is None:
        date_filter = "AND (e.ended_on IS NULL OR trim(e.ended_on) = '')"
    else:
        date_filter = """
              AND (e.started_on IS NULL OR trim(e.started_on) = '' OR date(e.started_on) <= date(?))
              AND (e.ended_on IS NULL OR trim(e.ended_on) = '' OR date(e.ended_on) >= date(?))
        """
    return f"""
                    {base_sql}
                      AND e.status = 'active'
                      AND s.active = 1
                      {date_filter}
                    {order_by}
                    """


def _active_enrollees_params(
    params: tuple[object, ...],
    *,
    session_date: str | None,
) -> tuple[object, ...]:
    if session_date is None:
        return params
    return (*params, session_date, session_date)


def _optional_option(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    index = args.index(name)
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = cast("int | str", row[key])
    return int(value)


def _row_str(row: sqlite3.Row, key: str) -> str:
    return cast("str", row[key])


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


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


def _registration_plan_id(template_id: str) -> str:
    return f"write-action:{template_id}"


def _register_approval_hint(approval_id: JsonValue) -> str:
    approval_text = approval_id if isinstance(approval_id, str) else "<approval-id>"
    return (
        "approve in a REAL terminal: python -m chat_lms_agent approval approve "
        f"--id {approval_text} --actor <you>"
    )


def _unregistered_apply_hint(approval_id: str) -> str:
    return (
        "register first: python -m chat_lms_agent write-action register --id <id> "
        "--profile-root <root> --json ; then approve in a REAL terminal: "
        "python -m chat_lms_agent approval approve "
        f"--id {approval_id} --actor <you>"
    )
