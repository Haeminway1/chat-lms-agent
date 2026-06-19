from __future__ import annotations

import json
from pathlib import Path

from chat_lms_agent.cli_io import option, required_option, subcommand, write_json
from chat_lms_agent.daily_management_outbound import (
    build_daily_management_journal_items,
    load_current_values,
)
from chat_lms_agent.outbound_sync import (
    OutboundItem,
    build_plan,
    ensure_outbound_ledger,
    outbound_item_from_json,
    outbound_item_to_json,
    record_outbound_result,
)

COMMAND_VERB_INDEX = 2


def handle_outbound(args: list[str], repo_root: Path) -> int:
    _ = repo_root
    command = subcommand(args)
    if command == "plan":
        return _plan(args)
    if command == "ledger":
        return _ledger(args)
    if command == "daily-management":
        return _daily_management(args)
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
    if verb != "journal-plan":
        write_json({"status": "ERROR", "error_code": "UNKNOWN_OUTBOUND_COMMAND"})
        return 2
    db_path = _db_path(args)
    source_key = option(args, "--source-key") or "daily_management.2026_06"
    start_date = required_option(args, "--from")
    end_date = required_option(args, "--to")
    current_values = load_current_values(Path(required_option(args, "--current-values-json")))
    out_dir = Path(required_option(args, "--out-dir"))
    out_dir.mkdir(parents=True, exist_ok=True)
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
        item for item in items if decisions.get(item.idempotency_key) in {"write_new", "write_changed"}
    ]
    already_verified_items = [
        item for item in items if decisions.get(item.idempotency_key) in {"skip_same", "skip_current_matches"}
    ]
    payload = plan["write_payload"]
    if not isinstance(payload, dict):
        write_json({"status": "ERROR", "error_code": "OUTBOUND_INVALID_PLAN"})
        return 2
    data = payload.get("data", [])
    paths = {
        "items": out_dir / "outbound_items.json",
        "write_items": out_dir / "write_items.json",
        "ledger_record_items": out_dir / "ledger_record_items.json",
        "sync_plan": out_dir / "sync_plan.json",
        "batch_update_payload": out_dir / "batch_update_payload.json",
    }
    _write_json_file(paths["items"], {"items": [outbound_item_to_json(item) for item in items]})
    _write_json_file(paths["write_items"], {"items": [outbound_item_to_json(item) for item in write_items]})
    _write_json_file(
        paths["ledger_record_items"],
        {"items": [outbound_item_to_json(item) for item in already_verified_items]},
    )
    _write_json_file(paths["sync_plan"], plan)
    _write_json_file(paths["batch_update_payload"], {"data": data})
    write_json(
        {
            "status": "PASS",
            "source_key": source_key,
            "summary": plan["summary"],
            "paths": {key: str(value) for key, value in paths.items()},
        },
    )
    return 0


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
