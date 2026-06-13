from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.academy_db import (
    academy_doctor_payload,
    apply_migration,
    apply_restore,
    build_report,
    create_backup,
    init_store,
    inspect_store,
    plan_migration,
    plan_restore,
    query_list_payload,
    run_query,
    schema_payload,
    spec_payload,
)
from chat_lms_agent.academy_db_imports import apply_import, plan_import
from chat_lms_agent.cli_io import (
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.record_store import add_record, list_records
from chat_lms_agent.record_types import record_types_list_json

if TYPE_CHECKING:
    from collections.abc import Callable

    from chat_lms_agent.state import JsonValue, ProfileState

QUERY_SUBCOMMAND_INDEX: Final = 2


def handle_academy_db(args: list[str], repo_root: Path) -> int:
    command = subcommand(args)
    if command == "spec":
        write_json(spec_payload())
        return 0
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    handlers: dict[str, Callable[[], int]] = {
        "init": lambda: _init(profile),
        "inspect": lambda: _inspect(profile),
        "schema": _schema,
        "query": lambda: _query(args, profile),
        "record-types": lambda: _record_types(args, profile, repo_root),
        "record": lambda: _record(args, profile, repo_root),
        "import": lambda: _import(args, profile, repo_root),
        "report": lambda: _report(args, profile),
        "backup": lambda: _backup(args, profile),
        "migrate": lambda: _migrate(args, profile),
        "restore": lambda: _restore(args),
        "doctor": _doctor,
    }
    handler = handlers.get(command)
    if handler is None:
        write_json({"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_DB_COMMAND"})
        return 2
    return handler()


def _init(profile: ProfileState) -> int:
    write_json(init_store(profile))
    return 0


def _inspect(profile: ProfileState) -> int:
    write_json(inspect_store(profile))
    return 0


def _schema() -> int:
    write_json(schema_payload())
    return 0


def _query(args: list[str], profile: ProfileState) -> int:
    query_command = args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    match query_command:
        case "list":
            write_json(query_list_payload())
            return 0
        case "run":
            params_path = option(args, "--params")
            payload = run_query(
                profile,
                required_option(args, "--name"),
                Path(params_path) if params_path is not None else None,
            )
            write_json(payload)
            return 0 if payload["status"] == "PASS" else 2
        case _:
            write_json({"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_QUERY_COMMAND"})
            return 2


def _record_types(args: list[str], profile: ProfileState, repo_root: Path) -> int:
    record_types_command = (
        args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    )
    match record_types_command:
        case "list":
            write_json(record_types_list_json(repo_root, profile))
            return 0
        case _:
            write_json(
                {"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_RECORD_TYPES_COMMAND"},
            )
            return 2


def _record(args: list[str], profile: ProfileState, repo_root: Path) -> int:
    record_command = args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    match record_command:
        case "add":
            code, payload = add_record(
                profile,
                repo_root,
                required_option(args, "--type"),
                required_option(args, "--learner"),
                _record_values(args),
            )
            write_json(payload)
            return code
        case "list":
            code, payload = list_records(
                profile,
                required_option(args, "--type"),
                required_option(args, "--learner"),
                _recent_option(args),
            )
            write_json(payload)
            return code
        case _:
            write_json({"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_RECORD_COMMAND"})
            return 2


def _record_values(args: list[str]) -> dict[str, JsonValue]:
    from_path = option(args, "--from")
    if from_path is not None:
        return _read_values_file(Path(from_path))
    values: dict[str, JsonValue] = {}
    for index, arg in enumerate(args[:-1]):
        if arg == "--set":
            pair = args[index + 1]
            if "=" in pair:
                key, value = pair.split("=", 1)
                values[key] = value
    return values


def _read_values_file(path: Path) -> dict[str, JsonValue]:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _recent_option(args: list[str]) -> int | None:
    raw = option(args, "--recent")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _import(args: list[str], profile: ProfileState, repo_root: Path) -> int:
    import_command = args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    source_path = Path(required_option(args, "--from"))
    payload: dict[str, JsonValue]
    match import_command:
        case "plan":
            payload = plan_import(profile, source_path, repo_root)
            write_json(payload)
            return 4 if payload["status"] == "UNSAFE" else 0
        case "apply":
            payload = apply_import(profile, source_path, repo_root, option(args, "--approval-id"))
            write_json(payload)
            if payload["status"] == "PASS":
                return 0
            if payload["status"] == "NEEDS_APPROVAL":
                return 3
            return 4 if payload["status"] == "UNSAFE" else 2
        case _:
            payload = {"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_IMPORT_COMMAND"}
            write_json(payload)
            return 2


def _report(args: list[str], profile: ProfileState) -> int:
    report_command = args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    if report_command != "build":
        write_json({"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_REPORT_COMMAND"})
        return 2
    write_json(build_report(profile, required_option(args, "--report")))
    return 0


def _backup(args: list[str], profile: ProfileState) -> int:
    backup_command = args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    if backup_command != "create":
        write_json({"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_BACKUP_COMMAND"})
        return 2
    write_json(create_backup(profile))
    return 0


def _migrate(args: list[str], profile: ProfileState) -> int:
    migrate_command = args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    payload: dict[str, JsonValue]
    match migrate_command:
        case "plan":
            payload = plan_migration(required_option(args, "--to"))
        case "apply":
            payload = apply_migration(profile, required_option(args, "--to"))
        case _:
            payload = {"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_MIGRATE_COMMAND"}
    write_json(payload)
    return 0 if payload["status"] == "PASS" else 2


def _restore(args: list[str]) -> int:
    restore_command = args[QUERY_SUBCOMMAND_INDEX] if len(args) > QUERY_SUBCOMMAND_INDEX else ""
    payload: dict[str, JsonValue]
    match restore_command:
        case "plan":
            payload = plan_restore()
        case "apply":
            payload = apply_restore(option(args, "--plan-id"))
        case _:
            payload = {"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_RESTORE_COMMAND"}
    write_json(payload)
    return 0 if payload["status"] == "PASS" else 2


def _doctor() -> int:
    write_json(academy_doctor_payload())
    return 0
