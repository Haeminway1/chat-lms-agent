from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from chat_lms_agent.record_store import list_records

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

RECORDS_SCHEMA_VERSION: Final = "records-panel-v1"
_ATTENDANCE_TYPE: Final = "attendance"
_TYPE_LABELS: Final[dict[str, str]] = {"attendance": "출결", "journal": "일지"}
_META_FIELDS: Final = frozenset({"type", "learner_id", "learner", "date"})


def records_panel_payload(
    profile: ProfileState,
    learner_ref: str,
    record_type: str,
    recent: int | None,
) -> dict[str, JsonValue]:
    _code, listing = list_records(profile, record_type, learner_ref, recent)
    records = _records(listing)
    label = _TYPE_LABELS.get(record_type, record_type)
    view_id = "attendance_summary" if record_type == _ATTENDANCE_TYPE else "learner_detail"
    items: list[JsonValue] = [_entity_item(record) for record in records]
    warnings: list[JsonValue] = []
    if not records:
        warnings.append({"level": "warning", "message": f"{label} 기록이 없습니다."})
    sections: list[JsonValue] = [
        {"type": "summary", "text": f"{learner_ref} {label} — 최근 {len(records)}건"},
        {"type": "entity_list", "items": items},
    ]
    return {
        "schema_version": RECORDS_SCHEMA_VERSION,
        "view_id": view_id,
        "title": f"{learner_ref} {label}",
        "subtitle": f"최근 {len(records)}건",
        "entity_ref": f"learner:{learner_ref}",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "privacy_level": "learner",
        "warnings": warnings,
        "sections": sections,
        "source_commands": [
            {
                "query_name": "academy-db-record-list",
                "command": (
                    "academy-db record list --type <type> --learner <name> "
                    "--profile-root <profile-root> --json"
                ),
            },
        ],
        "design_tokens": {
            "theme": "system",
            "accent": "#3182F6",
            "density": "comfy",
            "round": "soft",
            "fontSize": 15,
        },
    }


def _records(listing: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    raw = listing.get("records")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _entity_item(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    date = record.get("date")
    parts = [
        str(value)
        for key, value in record.items()
        if key not in _META_FIELDS and isinstance(value, str | int | float | bool)
    ]
    return {
        "label": str(date) if isinstance(date, str) else "기록",
        "value": " · ".join(parts),
    }
