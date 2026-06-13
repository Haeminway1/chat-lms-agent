from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

LEARNER_NAME_MISSING: Final = "LEARNER_NAME_MISSING"


def normalize_import_payload(
    payload: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    normalized = dict(payload)
    normalized["classes"] = _normalize_classes(payload.get("classes"))
    learners, missing_name_ids = _normalize_learners(payload.get("learners"))
    normalized["learners"] = learners
    lessons: list[JsonValue] = []
    lessons.extend(_json_object_values(payload.get("lessons")))
    normalized["lessons"] = lessons
    return normalized, _missing_name_warnings(missing_name_ids)


def import_plan_payload(
    payload: dict[str, JsonValue],
    source: dict[str, JsonValue],
    plan_id: str,
    approval_id: str,
) -> dict[str, JsonValue]:
    normalized, warnings = normalize_import_payload(payload)
    plan: dict[str, JsonValue] = {
        "status": "NEEDS_APPROVAL",
        "schema_version": "academy-import-plan-v1",
        "plan_id": plan_id,
        "approval_id": approval_id,
        "profile_root": "<profile-root>",
        "source": source.get("source", "<import-source>"),
        "writes": [],
        "preview": store_counts(normalized),
    }
    if warnings:
        plan["warnings"] = warnings
    return plan


def store_counts(store: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "classes": len(_list_value(store.get("classes"))),
        "learners": len(_list_value(store.get("learners"))),
        "lessons": len(_list_value(store.get("lessons"))),
    }


def _normalize_classes(value: JsonValue | None) -> list[JsonValue]:
    normalized: list[JsonValue] = []
    for item in _json_object_values(value):
        next_item = dict(item)
        if "id" not in next_item:
            class_id = next_item.get("class_id")
            if isinstance(class_id, str):
                next_item["id"] = class_id
        normalized.append(next_item)
    return normalized


def _normalize_learners(value: JsonValue | None) -> tuple[list[JsonValue], list[str]]:
    normalized: list[JsonValue] = []
    missing_name_ids: list[str] = []
    for item in _json_object_values(value):
        next_item = dict(item)
        if "id" not in next_item:
            learner_id = next_item.get("learner_id")
            if isinstance(learner_id, str):
                next_item["id"] = learner_id
        if "name" not in next_item:
            display_name = next_item.get("display_name")
            if isinstance(display_name, str):
                next_item["name"] = display_name
        name = next_item.get("name")
        learner_id = next_item.get("id")
        if not isinstance(name, str) and isinstance(learner_id, str):
            missing_name_ids.append(learner_id)
        normalized.append(next_item)
    return normalized, missing_name_ids


def _missing_name_warnings(missing_name_ids: list[str]) -> list[JsonValue]:
    if not missing_name_ids:
        return []
    ids: list[JsonValue] = []
    ids.extend(missing_name_ids)
    warning: dict[str, JsonValue] = {
        "code": LEARNER_NAME_MISSING,
        "entity": "learners",
        "ids": ids,
        "level": "warning",
        "message": "learner name is required for lesson panel display",
    }
    return [warning]


def _json_object_values(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _list_value(value: JsonValue | None) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return []
