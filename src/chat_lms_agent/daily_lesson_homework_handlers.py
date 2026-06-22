from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent.cli_io import option, required_option, write_json
from chat_lms_agent.daily_lesson_homework_db import connect
from chat_lms_agent.daily_lesson_homework_outbound import (
    DEFAULT_SOURCE_KEY,
    HomeworkMapping,
    load_homework_mapping,
)
from chat_lms_agent.daily_lesson_homework_plan_files import (
    PlanFileRequest,
    build_plan_files,
    read_items,
    read_json_object,
    write_json_file,
)
from chat_lms_agent.daily_lesson_homework_verify import verification_manifest
from chat_lms_agent.gws_api import sheets_batch_update, sheets_values_get
from chat_lms_agent.gws_auth import default_token_path, load_valid_access_token
from chat_lms_agent.outbound_sync import record_outbound_result

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

COMMAND_VERB_INDEX = 2


@dataclass(frozen=True, slots=True)
class ExecuteContext:
    db_path: Path
    access: str
    spreadsheet_id: str
    tab: str
    out_dir: Path
    summary: dict[str, JsonValue]


def handle_daily_lesson_homework(args: list[str]) -> int:
    verb = _third_verb(args)
    if verb == "plan":
        return _plan_command(args)
    if verb == "sync":
        return _sync_command(args)
    write_json({"status": "ERROR", "error_code": "UNKNOWN_OUTBOUND_COMMAND"})
    return 2


def _plan_command(args: list[str]) -> int:
    current_path = Path(required_option(args, "--current-values-json"))
    code, payload = build_plan_files(
        PlanFileRequest(
            _db_path(args),
            option(args, "--source-key") or DEFAULT_SOURCE_KEY,
            required_option(args, "--date"),
            read_json_object(current_path),
            _class_codes(args),
            Path(required_option(args, "--out-dir")),
        ),
    )
    write_json(payload)
    return code


def _sync_command(args: list[str]) -> int:
    db_path = _db_path(args)
    source_key = option(args, "--source-key") or DEFAULT_SOURCE_KEY
    lesson_date = required_option(args, "--date")
    tab = str(int(lesson_date[-2:]))
    out_dir = Path(required_option(args, "--out-dir"))
    out_dir.mkdir(parents=True, exist_ok=True)
    access = load_valid_access_token(_token_path(args))
    mapping = _load_mapping(db_path, source_key)
    current_values = sheets_values_get(access, mapping.spreadsheet_id, f"'{tab}'!A1:K1000")
    write_json_file(out_dir / "current_a_k.json", current_values)
    code, result = build_plan_files(
        PlanFileRequest(
            db_path,
            source_key,
            lesson_date,
            current_values,
            _class_codes(args),
            out_dir,
        ),
    )
    if code != 0:
        write_json(result)
        return code
    summary = _summary_dict(result)
    if _int_value(summary.get("review_conflict")) > 0:
        write_json(
            {
                "status": "BLOCKED",
                "error_code": "OUTBOUND_REVIEW_CONFLICT",
                "summary": summary,
                "conflict_report": str(out_dir / "conflict_report.json"),
            },
        )
        return 5
    if not _has_flag(args, "--execute"):
        write_json(
            {
                "status": "PASS",
                "execute_required": True,
                "summary": summary,
                "out_dir": str(out_dir),
            },
        )
        return 0
    return _execute_and_verify(
        ExecuteContext(db_path, access, mapping.spreadsheet_id, tab, out_dir, summary),
    )


def _execute_and_verify(context: ExecuteContext) -> int:
    payload = read_json_object(context.out_dir / "batch_update_payload.json")
    data = payload.get("data", [])
    updates = _update_list(data)
    if updates:
        _ = sheets_batch_update(context.access, context.spreadsheet_id, updates)
    post_values = sheets_values_get(
        context.access,
        context.spreadsheet_id,
        f"'{context.tab}'!A1:K1000",
    )
    post_safety = sheets_values_get(
        context.access,
        context.spreadsheet_id,
        f"'{context.tab}'!P1:Z1000",
    )
    write_json_file(context.out_dir / "post_a_k.json", post_values)
    write_json_file(context.out_dir / "post_p_z.json", post_safety)
    manifest = verification_manifest(payload, post_values, post_safety)
    write_json_file(context.out_dir / "sync_manifest.json", manifest)
    if manifest["status"] != "PASS":
        write_json(
            {
                "status": "ERROR",
                "error_code": "OUTBOUND_VERIFY_FAILED",
                "manifest": manifest,
            },
        )
        return 6
    recorded = _record_items(context.db_path, context.out_dir / "ledger_record_items.json")
    recorded += _record_items(context.db_path, context.out_dir / "write_items.json")
    write_json(
        {
            "status": "PASS",
            "summary": context.summary,
            "verified": manifest["verified_count"],
            "recorded": recorded,
        },
    )
    return 0


def _load_mapping(db_path: Path, source_key: str) -> HomeworkMapping:
    conn = connect(db_path)
    try:
        return load_homework_mapping(conn, source_key)
    finally:
        conn.close()


def _record_items(db_path: Path, path: Path) -> int:
    items = read_items(path)
    for item in items:
        record_outbound_result(
            db_path,
            item,
            status="verified",
            external_row_hash=item.content_hash,
        )
    return len(items)


def _summary_dict(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    summary = payload.get("summary")
    return cast("dict[str, JsonValue]", summary) if isinstance(summary, dict) else {}


def _update_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    return [cast("dict[str, JsonValue]", item) for item in value if isinstance(item, dict)]


def _int_value(value: JsonValue | None) -> int:
    if isinstance(value, bool | dict | list) or value is None:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _class_codes(args: list[str]) -> tuple[str, ...]:
    raw = option(args, "--classes")
    if raw is None:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _db_path(args: list[str]) -> Path:
    value = option(args, "--db") or option(args, "--database")
    if value is None:
        value = required_option(args, "--db")
    return Path(value)


def _has_flag(args: list[str], flag: str) -> bool:
    return flag in args


def _third_verb(args: list[str]) -> str | None:
    rest = args[COMMAND_VERB_INDEX:] if len(args) > COMMAND_VERB_INDEX else []
    for token in rest:
        if not token.startswith("-"):
            return token
    return None


def _token_path(args: list[str]) -> Path:
    override = option(args, "--token-file")
    return Path(override) if override else default_token_path()
