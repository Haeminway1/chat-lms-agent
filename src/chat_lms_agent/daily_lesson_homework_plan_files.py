from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from chat_lms_agent.daily_lesson_homework_outbound import build_daily_lesson_homework_items
from chat_lms_agent.outbound_sync import (
    OutboundItem,
    build_plan,
    outbound_item_from_json,
    outbound_item_to_json,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue


@dataclass(frozen=True, slots=True)
class PlanFileRequest:
    db_path: Path
    source_key: str
    lesson_date: str
    current_values: dict[str, JsonValue]
    class_codes: tuple[str, ...]
    out_dir: Path


def build_plan_files(request: PlanFileRequest) -> tuple[int, dict[str, JsonValue]]:
    request.out_dir.mkdir(parents=True, exist_ok=True)
    items = build_daily_lesson_homework_items(
        request.db_path,
        source_key=request.source_key,
        lesson_date=request.lesson_date,
        current_values_payload=request.current_values,
        class_codes=request.class_codes,
    )
    return _write_plan_files(request.db_path, request.source_key, request.out_dir, items)


def read_items(plan_path: Path) -> list[OutboundItem]:
    payload = read_json_object(plan_path)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        message = "plan.items must be a list"
        raise TypeError(message)
    return [outbound_item_from_json(raw) for raw in raw_items]


def read_json_object(path: Path) -> dict[str, JsonValue]:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8-sig")))
    if not isinstance(payload, dict):
        message = "JSON payload must be an object"
        raise TypeError(message)
    return cast("dict[str, JsonValue]", payload)


def write_json_file(path: Path, payload: JsonValue) -> None:
    _ = path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_plan_files(
    db_path: Path,
    source_key: str,
    out_dir: Path,
    items: list[OutboundItem],
) -> tuple[int, dict[str, JsonValue]]:
    plan = build_plan(db_path, items)
    payload = plan["write_payload"]
    if not isinstance(payload, dict):
        return 2, {"status": "ERROR", "error_code": "OUTBOUND_INVALID_PLAN"}
    write_payload = cast("dict[str, JsonValue]", payload)
    decisions = _plan_decisions(plan)
    write_items = _items_with_decision(items, decisions, {"write_new", "write_changed"})
    verified_items = _items_with_decision(items, decisions, {"skip_same", "skip_current_matches"})
    paths = _plan_paths(out_dir)
    write_json_file(paths["items"], _item_payload(items))
    write_json_file(paths["write_items"], _item_payload(write_items))
    write_json_file(paths["ledger_record_items"], _item_payload(verified_items))
    write_json_file(paths["sync_plan"], plan)
    write_json_file(paths["batch_update_payload"], {"data": write_payload.get("data", [])})
    write_json_file(paths["preview"], _preview(plan))
    write_json_file(paths["conflict_report"], _conflict_report(plan))
    return 0, {
        "status": "PASS",
        "source_key": source_key,
        "summary": plan["summary"],
        "paths": {key: str(value) for key, value in paths.items()},
    }


def _items_with_decision(
    items: list[OutboundItem],
    decisions: dict[str, str],
    allowed: set[str],
) -> list[OutboundItem]:
    return [item for item in items if decisions.get(item.idempotency_key) in allowed]


def _plan_paths(out_dir: Path) -> dict[str, Path]:
    return {
        "items": out_dir / "outbound_items.json",
        "write_items": out_dir / "write_items.json",
        "ledger_record_items": out_dir / "ledger_record_items.json",
        "sync_plan": out_dir / "sync_plan.json",
        "batch_update_payload": out_dir / "batch_update_payload.json",
        "preview": out_dir / "preview.json",
        "conflict_report": out_dir / "conflict_report.json",
    }


def _preview(plan: dict[str, JsonValue]) -> dict[str, JsonValue]:
    items = plan.get("items", [])
    rows = items if isinstance(items, list) else []
    return {
        "summary": plan.get("summary", {}),
        "preview": [
            {
                "range": raw.get("range"),
                "current": raw.get("current_value"),
                "target": raw.get("target_value"),
                "decision": raw.get("decision"),
            }
            for raw in rows
            if isinstance(raw, dict)
        ],
    }


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


def _plan_decisions(plan: dict[str, JsonValue]) -> dict[str, str]:
    items = plan.get("items", [])
    rows = items if isinstance(items, list) else []
    decisions: dict[str, str] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key = raw.get("idempotency_key")
        decision = raw.get("decision")
        if key is not None and decision is not None:
            decisions[str(key)] = str(decision)
    return decisions


def _item_payload(items: list[OutboundItem]) -> dict[str, JsonValue]:
    return {"items": [outbound_item_to_json(item) for item in items]}
