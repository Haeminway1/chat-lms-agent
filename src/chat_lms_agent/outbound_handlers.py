from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent.cli_io import option, required_option, subcommand, write_json
from chat_lms_agent.daily_lesson_homework_handlers import handle_daily_lesson_homework
from chat_lms_agent.daily_lesson_homework_verify import verification_manifest
from chat_lms_agent.daily_management_outbound import (
    JournalMapping,
    build_daily_management_journal_items,
    current_values_from_json,
    journal_read_range,
    load_current_values,
    load_journal_mapping,
)
from chat_lms_agent.gws_api import sheets_batch_update, sheets_values_get
from chat_lms_agent.gws_auth import default_token_path, load_valid_access_token
from chat_lms_agent.outbound_sync import (
    OutboundItem,
    build_plan,
    ensure_outbound_ledger,
    outbound_item_from_json,
    outbound_item_to_json,
    record_outbound_result,
)

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

COMMAND_VERB_INDEX = 2


@dataclass(frozen=True, slots=True)
class _DmPlanResult:
    plan: dict[str, JsonValue]
    write_items: list[OutboundItem]
    verified_items: list[OutboundItem]
    data: list[JsonValue]
    paths: dict[str, Path]


def handle_outbound(args: list[str], repo_root: Path) -> int:
    _ = repo_root
    command = subcommand(args)
    if command == "plan":
        return _plan(args)
    if command == "ledger":
        return _ledger(args)
    if command == "daily-management":
        return _daily_management(args)
    if command == "daily-lesson-homework":
        return handle_daily_lesson_homework(args)
    write_json({"status": "ERROR", "error_code": "UNKNOWN_OUTBOUND_COMMAND"})
    return 2


def _plan(args: list[str]) -> int:
    db_path = _db_path(args)
    plan_path = Path(required_option(args, "--from-json"))
    try:
        items = _read_items(plan_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        write_json(
            {
                "status": "ERROR",
                "error_code": "OUTBOUND_INVALID_PLAN",
                "message": str(error),
            },
        )
        return 2
    write_json(build_plan(db_path, items))
    return 0


def _ledger(args: list[str]) -> int:
    verb = _third_verb(args)
    if verb == "init":
        db_path = _db_path(args)
        ensure_outbound_ledger(db_path)
        write_json(
            {
                "status": "PASS",
                "ledger": "external_outbound_ledger",
                "db": "<db>",
            },
        )
        return 0
    if verb == "record":
        db_path = _db_path(args)
        items = _read_items(Path(required_option(args, "--from-json")))
        status = required_option(args, "--status")
        for item in items:
            record_outbound_result(
                db_path,
                item,
                status=status,
                external_row_hash=item.content_hash,
            )
        write_json(
            {
                "status": "PASS",
                "recorded": len(items),
                "ledger": "external_outbound_ledger",
            },
        )
        return 0
    write_json({"status": "ERROR", "error_code": "UNKNOWN_OUTBOUND_COMMAND"})
    return 2


def _daily_management(args: list[str]) -> int:
    verb = _third_verb(args)
    if verb == "journal-plan":
        return _daily_management_journal_plan(args)
    if verb == "sync":
        return _daily_management_sync(args)
    write_json({"status": "ERROR", "error_code": "UNKNOWN_OUTBOUND_COMMAND"})
    return 2


def _daily_management_journal_plan(args: list[str]) -> int:
    db_path = _db_path(args)
    source_key = option(args, "--source-key") or "daily_management.2026_06"
    start_date = required_option(args, "--from")
    end_date = required_option(args, "--to")
    current_values = load_current_values(Path(required_option(args, "--current-values-json")))
    out_dir = Path(required_option(args, "--out-dir"))
    out_dir.mkdir(parents=True, exist_ok=True)
    result = _daily_management_plan_files(
        db_path,
        source_key,
        start_date,
        end_date,
        current_values,
        out_dir,
    )
    if result is None:
        write_json({"status": "ERROR", "error_code": "OUTBOUND_INVALID_PLAN"})
        return 2
    write_json(
        {
            "status": "PASS",
            "source_key": source_key,
            "summary": result.plan["summary"],
            "paths": {key: str(value) for key, value in result.paths.items()},
        },
    )
    return 0


def _daily_management_sync(args: list[str]) -> int:
    db_path = _db_path(args)
    source_key = option(args, "--source-key") or "daily_management.2026_06"
    date_range = _date_range(args)
    if date_range is None:
        write_json(
            {
                "status": "ERROR",
                "error_code": "INVALID_ARGUMENT",
                "message": "daily-management sync needs --date or --from/--to",
            },
        )
        return 2
    start_date, end_date = date_range
    out_dir = Path(required_option(args, "--out-dir"))
    out_dir.mkdir(parents=True, exist_ok=True)
    access = load_valid_access_token(_token_path(args))
    mapping = load_journal_mapping(db_path, source_key)
    read_range = journal_read_range(mapping)
    current_raw = sheets_values_get(access, mapping.spreadsheet_id, read_range)
    _write_json_file(out_dir / "current_values.json", current_raw)
    current_values = current_values_from_json(current_raw)
    result = _daily_management_plan_files(
        db_path,
        source_key,
        start_date,
        end_date,
        current_values,
        out_dir,
    )
    if result is None:
        write_json({"status": "ERROR", "error_code": "OUTBOUND_INVALID_PLAN"})
        return 2
    summary = result.plan["summary"]
    if _summary_int(summary, "review_conflict") > 0:
        write_json(
            {
                "status": "BLOCKED",
                "error_code": "OUTBOUND_REVIEW_CONFLICT",
                "summary": summary,
                "conflict_report": str(out_dir / "conflict_report.json"),
            },
        )
        return 5
    if "--execute" not in args:
        write_json(
            {
                "status": "PASS",
                "execute_required": True,
                "summary": summary,
                "out_dir": str(out_dir),
            },
        )
        return 0
    return _daily_management_execute(db_path, access, mapping, read_range, result, summary, out_dir)


def _daily_management_execute(  # noqa: PLR0913 - explicit execute context
    db_path: Path,
    access: str,
    mapping: JournalMapping,
    read_range: str,
    result: _DmPlanResult,
    summary: JsonValue,
    out_dir: Path,
) -> int:
    updates = cast(
        "list[dict[str, JsonValue]]",
        [update for update in result.data if isinstance(update, dict)],
    )
    if updates:
        _ = sheets_batch_update(access, mapping.spreadsheet_id, updates)
    post_values = sheets_values_get(access, mapping.spreadsheet_id, read_range)
    _write_json_file(out_dir / "post_values.json", post_values)
    manifest = verification_manifest({"data": result.data}, post_values, {"values": []})
    _write_json_file(out_dir / "sync_manifest.json", manifest)
    if manifest["status"] != "PASS":
        write_json(
            {"status": "ERROR", "error_code": "OUTBOUND_VERIFY_FAILED", "manifest": manifest},
        )
        return 6
    recorded = _record_dm_items(db_path, result.write_items)
    recorded += _record_dm_items(db_path, result.verified_items)
    write_json(
        {
            "status": "PASS",
            "summary": summary,
            "verified": manifest["verified_count"],
            "recorded": recorded,
        },
    )
    return 0


def _daily_management_plan_files(  # noqa: PLR0913 - mirrors the journal item builder surface
    db_path: Path,
    source_key: str,
    start_date: str,
    end_date: str,
    current_values: dict[str, str],
    out_dir: Path,
) -> _DmPlanResult | None:
    items = build_daily_management_journal_items(
        db_path,
        source_key=source_key,
        start_date=start_date,
        end_date=end_date,
        current_values=current_values,
    )
    plan = build_plan(db_path, items)
    decisions = {
        str(raw.get("idempotency_key")): str(raw.get("decision"))
        for raw in plan["items"]
        if isinstance(raw, dict)
    }
    write_items = [
        item
        for item in items
        if decisions.get(item.idempotency_key) in {"write_new", "write_changed"}
    ]
    already_verified_items = [
        item
        for item in items
        if decisions.get(item.idempotency_key) in {"skip_same", "skip_current_matches"}
    ]
    payload = plan["write_payload"]
    if not isinstance(payload, dict):
        return None
    data = cast("list[JsonValue]", payload.get("data", []))
    paths = {
        "items": out_dir / "outbound_items.json",
        "write_items": out_dir / "write_items.json",
        "ledger_record_items": out_dir / "ledger_record_items.json",
        "sync_plan": out_dir / "sync_plan.json",
        "batch_update_payload": out_dir / "batch_update_payload.json",
        "conflict_report": out_dir / "conflict_report.json",
    }
    _write_json_file(paths["items"], {"items": [outbound_item_to_json(item) for item in items]})
    _write_json_file(
        paths["write_items"],
        {"items": [outbound_item_to_json(item) for item in write_items]},
    )
    _write_json_file(
        paths["ledger_record_items"],
        {"items": [outbound_item_to_json(item) for item in already_verified_items]},
    )
    _write_json_file(paths["sync_plan"], plan)
    _write_json_file(paths["batch_update_payload"], {"data": data})
    _write_json_file(paths["conflict_report"], _conflict_report(plan))
    return _DmPlanResult(plan, write_items, already_verified_items, data, paths)


def _conflict_report(plan: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Per-cell review-conflict detail so a blocked sync is reviewable, not a dead end."""
    items = plan.get("items", [])
    rows = items if isinstance(items, list) else []
    conflicts: list[JsonValue] = [
        {
            "range": raw.get("range"),
            "current": raw.get("current_value"),
            "target": raw.get("target_value"),
            "idempotency_key": raw.get("idempotency_key"),
        }
        for raw in rows
        if isinstance(raw, dict) and raw.get("decision") == "review_conflict"
    ]
    return {"count": len(conflicts), "conflicts": conflicts}


def _date_range(args: list[str]) -> tuple[str, str] | None:
    single = option(args, "--date")
    if single:
        return single, single
    start = option(args, "--from")
    end = option(args, "--to")
    if start and end:
        return start, end
    return None


def _summary_int(summary: JsonValue, key: str) -> int:
    if not isinstance(summary, dict):
        return 0
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _record_dm_items(db_path: Path, items: list[OutboundItem]) -> int:
    for item in items:
        record_outbound_result(
            db_path,
            item,
            status="verified",
            external_row_hash=item.content_hash,
        )
    return len(items)


def _token_path(args: list[str]) -> Path:
    override = option(args, "--token-file")
    return Path(override) if override else default_token_path()


def _read_items(plan_path: Path) -> list[OutboundItem]:
    payload = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        message = "plan must be a JSON object"
        raise TypeError(message)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        message = "plan.items must be a list"
        raise TypeError(message)
    return [outbound_item_from_json(raw) for raw in raw_items]


def _write_json_file(path: Path, payload: object) -> None:
    _ = path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _db_path(args: list[str]) -> Path:
    value = option(args, "--db") or option(args, "--database")
    if value is None:
        value = required_option(args, "--db")
    return Path(value)


def _third_verb(args: list[str]) -> str | None:
    rest = args[COMMAND_VERB_INDEX:] if len(args) > COMMAND_VERB_INDEX else []
    for token in rest:
        if not token.startswith("-"):
            return token
    return None
