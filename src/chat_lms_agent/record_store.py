from __future__ import annotations

from typing import TYPE_CHECKING, Final

from chat_lms_agent.academy_db import read_store, write_store
from chat_lms_agent.journal import write_audit, write_trace
from chat_lms_agent.record_types import load_record_types
from chat_lms_agent.record_validation import validate_record_values

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.record_types import RecordType
    from chat_lms_agent.state import JsonValue, ProfileState

RECORD_STORE_KEY: Final = "records"


def add_record(
    profile: ProfileState,
    repo_root: Path,
    type_id: str,
    learner_ref: str,
    values: dict[str, JsonValue],
) -> tuple[int, dict[str, JsonValue]]:
    record_type = _find_type(repo_root, profile, type_id)
    if record_type is None:
        return 2, {"status": "ERROR", "error_code": "UNKNOWN_RECORD_TYPE", "type": type_id}
    store = read_store(profile)
    learner = _resolve_learner(store, learner_ref)
    if learner is None:
        return 2, {
            "status": "ERROR",
            "error_code": "UNRESOLVABLE_LEARNER",
            "learner": learner_ref,
        }
    errors = validate_record_values(record_type, values)
    if errors:
        error_list: list[JsonValue] = [*errors]
        return 2, {"status": "ERROR", "error_code": "INVALID_RECORD", "errors": error_list}
    learner_id = _learner_id(learner)
    record: dict[str, JsonValue] = {"type": type_id, "learner_id": learner_id, **values}
    records = _record_list(store)
    records.append(record)
    record_values: list[JsonValue] = [*records]
    store[RECORD_STORE_KEY] = record_values
    write_store(profile, store)
    details: dict[str, JsonValue] = {"type": type_id, "learner_id": learner_id}
    _ = write_trace(profile, "academy_record_added", "Academy record added.", details)
    _ = write_audit(
        profile,
        "academy-db.record.add",
        "Academy record appended to the store.",
        details,
    )
    return 0, {"status": "PASS", "record": record, "count": len(records)}


def list_records(
    profile: ProfileState,
    type_id: str,
    learner_ref: str,
    recent: int | None,
) -> tuple[int, dict[str, JsonValue]]:
    store = read_store(profile)
    learner = _resolve_learner(store, learner_ref)
    learner_id = _learner_id(learner) if learner is not None else None
    matched = [
        record
        for record in _record_list(store)
        if record.get("type") == type_id and _matches_learner(record, learner_id, learner_ref)
    ]
    matched.sort(key=_record_date, reverse=True)
    if recent is not None:
        matched = matched[:recent]
    records: list[JsonValue] = [*matched]
    return 0, {"status": "PASS", "type": type_id, "records": records, "count": len(matched)}


def _find_type(repo_root: Path, profile: ProfileState, type_id: str) -> RecordType | None:
    record_types, _warnings = load_record_types(repo_root, profile)
    for record_type in record_types:
        if record_type.type_id == type_id:
            return record_type
    return None


def _resolve_learner(
    store: dict[str, JsonValue],
    learner_ref: str,
) -> dict[str, JsonValue] | None:
    learners = store.get("learners")
    if not isinstance(learners, list):
        return None
    for item in learners:
        if not isinstance(item, dict):
            continue
        if learner_ref in (item.get("name"), item.get("id"), item.get("learner_id")):
            return item
    return None


def _learner_id(learner: dict[str, JsonValue]) -> str:
    for key in ("id", "learner_id"):
        value = learner.get(key)
        if isinstance(value, str) and value:
            return value
    name = learner.get("name")
    return name if isinstance(name, str) else ""


def _record_list(store: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    raw = store.get(RECORD_STORE_KEY)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _matches_learner(
    record: dict[str, JsonValue],
    learner_id: str | None,
    learner_ref: str,
) -> bool:
    if learner_id is not None and record.get("learner_id") == learner_id:
        return True
    return learner_ref in (record.get("learner"), record.get("learner_id"))


def _record_date(record: dict[str, JsonValue]) -> str:
    value = record.get("date")
    return value if isinstance(value, str) else ""
