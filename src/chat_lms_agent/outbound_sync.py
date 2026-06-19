from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

OutboundMode = Literal["append", "update", "clear"]
OutboundDecision = Literal[
    "skip_same",
    "skip_current_matches",
    "write_new",
    "write_changed",
    "review_conflict",
    "clear_obsolete",
]

LEDGER_TABLE = "external_outbound_ledger"
LEDGER_SCHEMA_VERSION = "external-outbound-ledger-v1"


@dataclass(frozen=True, slots=True)
class OutboundItem:
    source_key: str
    logical_entity: str
    local_ids: tuple[str, ...]
    target_period: str
    target_role: str
    schema_version: str
    mode: OutboundMode
    spreadsheet_id: str
    sheet_name: str
    range_a1: str
    target_value: JsonValue
    current_value: JsonValue
    payload: dict[str, JsonValue]

    @property
    def idempotency_key(self) -> str:
        """Stable logical identity used to prevent duplicate outbound writes."""
        return idempotency_key(
            source_key=self.source_key,
            logical_entity=self.logical_entity,
            local_ids=self.local_ids,
            target_period=self.target_period,
            target_role=self.target_role,
            schema_version=self.schema_version,
        )

    @property
    def content_hash(self) -> str:
        """Hash of the normalized target value intended for the external sheet."""
        return content_hash(self.target_value)


def idempotency_key(  # noqa: PLR0913 - public key surface mirrors the key tuple.
    *,
    source_key: str,
    logical_entity: str,
    local_ids: list[str] | tuple[str, ...],
    target_period: str,
    target_role: str,
    schema_version: str,
) -> str:
    local_key = ",".join(sorted(_normalize_key_part(part) for part in local_ids))
    parts = (
        _normalize_key_part(source_key),
        _normalize_key_part(logical_entity),
        local_key,
        _normalize_key_part(target_period),
        _normalize_key_part(target_role),
        _normalize_key_part(schema_version),
    )
    return "|".join(parts)


def normalize_for_hash(value: JsonValue) -> JsonValue:
    if value is None:
        return ""
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]
    return {key: normalize_for_hash(value[key]) for key in sorted(value)}


def content_hash(value: JsonValue) -> str:
    normalized = normalize_for_hash(value)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_outbound_ledger(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS external_outbound_ledger (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_key TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              provider TEXT NOT NULL DEFAULT 'google_sheets',
              spreadsheet_id TEXT NOT NULL,
              sheet_name TEXT NOT NULL DEFAULT '',
              range_a1 TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL,
              external_row_hash TEXT,
              payload_json TEXT NOT NULL DEFAULT '{}',
              schema_version TEXT NOT NULL DEFAULT 'external-outbound-ledger-v1',
              first_written_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              last_verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(source_key, idempotency_key)
            )
            """,
        )
        conn.commit()
    finally:
        conn.close()


def record_outbound_result(
    db_path: str | Path,
    item: OutboundItem,
    *,
    status: str,
    external_row_hash: str | None = None,
) -> None:
    ensure_outbound_ledger(db_path)
    conn = _connect(db_path)
    try:
        payload: dict[str, JsonValue] = {
            "logical_entity": item.logical_entity,
            "local_ids": list(item.local_ids),
            "target_period": item.target_period,
            "target_role": item.target_role,
            "mode": item.mode,
            "payload": item.payload,
        }
        conn.execute(
            """
            INSERT INTO external_outbound_ledger (
              source_key, idempotency_key, content_hash, spreadsheet_id, sheet_name,
              range_a1, status, external_row_hash, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key, idempotency_key) DO UPDATE SET
              content_hash=excluded.content_hash,
              spreadsheet_id=excluded.spreadsheet_id,
              sheet_name=excluded.sheet_name,
              range_a1=excluded.range_a1,
              status=excluded.status,
              external_row_hash=excluded.external_row_hash,
              payload_json=excluded.payload_json,
              last_verified_at=CURRENT_TIMESTAMP,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                item.source_key,
                item.idempotency_key,
                item.content_hash,
                item.spreadsheet_id,
                item.sheet_name,
                item.range_a1,
                status,
                external_row_hash,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def build_plan(db_path: str | Path, items: list[OutboundItem]) -> dict[str, JsonValue]:
    ensure_outbound_ledger(db_path)
    conn = _connect(db_path)
    try:
        planned_items: list[JsonValue] = []
        data: list[JsonValue] = []
        rows: list[JsonValue] = []
        clear_ranges: list[JsonValue] = []
        counts: dict[str, int] = {"total": len(items)}
        for item in items:
            entry = _ledger_entry(conn, item.source_key, item.idempotency_key)
            decision = _decide(item, entry)
            counts[decision] = counts.get(decision, 0) + 1
            planned_items.append(_planned_item(item, decision))
            if decision not in {"write_new", "write_changed", "clear_obsolete"}:
                continue
            if item.mode == "append":
                rows.append(_row_values(item.target_value))
            elif item.mode == "clear":
                clear_ranges.append(item.range_a1)
            else:
                data.append({"range": item.range_a1, "values": _sheet_values(item.target_value)})
        return {
            "status": "PASS",
            "schema_version": "outbound-plan-v1",
            "summary": counts,
            "items": planned_items,
            "write_payload": {
                "data": data,
                "rows": rows,
                "clear_ranges": clear_ranges,
            },
        }
    finally:
        conn.close()


def outbound_item_from_json(raw: object) -> OutboundItem:
    if not isinstance(raw, dict):
        message = "outbound item must be an object"
        raise TypeError(message)
    mode = raw.get("mode")
    if mode not in {"append", "update", "clear"}:
        message = "outbound item mode must be append, update, or clear"
        raise ValueError(message)
    local_ids = raw.get("local_ids")
    if not isinstance(local_ids, list) or not all(isinstance(item, str) for item in local_ids):
        message = "outbound item local_ids must be a list of strings"
        raise TypeError(message)
    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        message = "outbound item payload must be an object"
        raise TypeError(message)
    return OutboundItem(
        source_key=_required_str(raw, "source_key"),
        logical_entity=_required_str(raw, "logical_entity"),
        local_ids=tuple(local_ids),
        target_period=_required_str(raw, "target_period"),
        target_role=_required_str(raw, "target_role"),
        schema_version=_required_str(raw, "schema_version"),
        mode=cast("OutboundMode", mode),
        spreadsheet_id=_required_str(raw, "spreadsheet_id"),
        sheet_name=_required_str(raw, "sheet_name"),
        range_a1=_required_str(raw, "range_a1"),
        target_value=cast("JsonValue", raw.get("target_value")),
        current_value=cast("JsonValue", raw.get("current_value")),
        payload=cast("dict[str, JsonValue]", payload),
    )


def outbound_item_to_json(item: OutboundItem) -> dict[str, JsonValue]:
    return {
        "source_key": item.source_key,
        "logical_entity": item.logical_entity,
        "local_ids": list(item.local_ids),
        "target_period": item.target_period,
        "target_role": item.target_role,
        "schema_version": item.schema_version,
        "mode": item.mode,
        "spreadsheet_id": item.spreadsheet_id,
        "sheet_name": item.sheet_name,
        "range_a1": item.range_a1,
        "target_value": item.target_value,
        "current_value": item.current_value,
        "payload": item.payload,
    }


def _decide(item: OutboundItem, entry: sqlite3.Row | None) -> OutboundDecision:
    if item.mode == "append":
        return _decide_append(item, entry)
    if item.mode == "clear":
        return _decide_clear(item)
    return _decide_update(item, entry)


def _decide_append(item: OutboundItem, entry: sqlite3.Row | None) -> OutboundDecision:
    if entry is None:
        return "write_new"
    if _row_str(entry, "content_hash") == item.content_hash:
        return "skip_same"
    if _row_str(entry, "external_row_hash") == item.content_hash:
        return "skip_same"
    return "review_conflict"


def _decide_clear(item: OutboundItem) -> OutboundDecision:
    if normalize_for_hash(item.current_value) == "":
        return "skip_current_matches"
    return "clear_obsolete"


def _decide_update(item: OutboundItem, entry: sqlite3.Row | None) -> OutboundDecision:
    if normalize_for_hash(item.current_value) == normalize_for_hash(item.target_value):
        return "skip_current_matches"
    if item.payload.get("overwrite_policy") == "protect_non_empty":
        current_hash = content_hash(item.current_value)
        if normalize_for_hash(item.current_value) == "":
            return "write_changed"
        if entry is not None and (
            _row_str(entry, "content_hash") == current_hash
            or _row_str(entry, "external_row_hash") == current_hash
        ):
            return "write_changed"
        return "review_conflict"
    return "write_changed"


def _planned_item(item: OutboundItem, decision: OutboundDecision) -> dict[str, JsonValue]:
    return {
        "source_key": item.source_key,
        "logical_entity": item.logical_entity,
        "local_ids": list(item.local_ids),
        "target_period": item.target_period,
        "target_role": item.target_role,
        "schema_version": item.schema_version,
        "idempotency_key": item.idempotency_key,
        "content_hash": item.content_hash,
        "current_hash": content_hash(item.current_value),
        "decision": decision,
        "mode": item.mode,
        "range": item.range_a1,
        "spreadsheet_id": item.spreadsheet_id,
        "sheet_name": item.sheet_name,
        "target_value": item.target_value,
        "current_value": item.current_value,
        "payload": item.payload,
    }


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ledger_entry(conn: sqlite3.Connection, source_key: str, key: str) -> sqlite3.Row | None:
    row = conn.execute(
        """
        SELECT *
        FROM external_outbound_ledger
        WHERE source_key = ? AND idempotency_key = ?
        """,
        (source_key, key),
    ).fetchone()
    return cast("sqlite3.Row | None", row)


def _row_values(value: JsonValue) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return [value]


def _sheet_values(value: JsonValue) -> list[JsonValue]:
    if value == "":
        return [[""]]
    if isinstance(value, list):
        if value and all(isinstance(item, list) for item in value):
            return cast("list[JsonValue]", value)
        return [value]
    return [[value]]


def _required_str(raw: dict[object, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        message = f"outbound item missing string field: {key}"
        raise ValueError(message)
    return value


def _row_str(row: sqlite3.Row, key: str) -> str:
    value = row[key]
    return value if isinstance(value, str) else ""


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _normalize_key_part(value: str) -> str:
    return _normalize_text(value).replace("|", "/").replace(",", ";")
