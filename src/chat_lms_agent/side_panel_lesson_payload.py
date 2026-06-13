from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.academy_db import store_path

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

LESSON_VIEW_ID: Final = "lesson_prep"
LESSON_SCHEMA_VERSION: Final = "lesson-panel-v1"


def lesson_panel_payload(
    profile: ProfileState,
    student: str,
    lesson_date: str | None,
) -> dict[str, JsonValue]:
    store, store_warning = _read_academy_store(profile)
    learner = _find_learner(store, student)
    lesson = _find_lesson(store, student, learner, lesson_date)
    class_item = _find_class(store, learner)
    payload: dict[str, JsonValue] = {
        "schema_version": LESSON_SCHEMA_VERSION,
        "view_id": LESSON_VIEW_ID,
        "title": f"{student} 수업 준비",
        "subtitle": lesson_date or "날짜 미지정",
        "entity_ref": f"learner:{student}",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "privacy_level": "learner",
        "warnings": _warnings(store_warning, learner, lesson),
        "sections": _sections(student, lesson, learner, class_item),
        "source_commands": [
            {
                "query_name": "academy-db-inspect",
                "command": "academy-db inspect --profile-root <profile-root> --json",
            },
            {
                "query_name": "academy-db-query-list",
                "command": "academy-db query list --profile-root <profile-root> --json",
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
    return payload


def _read_academy_store(profile: ProfileState) -> tuple[dict[str, JsonValue], str | None]:
    path = store_path(profile)
    if not path.exists():
        return {}, "academy store is missing"
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return {}, "academy store could not be read"
    if isinstance(payload, dict):
        return payload, None
    return {}, "academy store top-level payload is not an object"


def _find_learner(store: dict[str, JsonValue], student: str) -> dict[str, JsonValue] | None:
    for item in _dict_items(store.get("learners")):
        if (
            item.get("name") == student
            or item.get("id") == student
            or item.get("learner_id") == student
        ):
            return item
    return None


def _find_lesson(
    store: dict[str, JsonValue],
    student: str,
    learner: dict[str, JsonValue] | None,
    lesson_date: str | None,
) -> dict[str, JsonValue] | None:
    learner_id = _learner_id(learner)
    for item in _dict_items(store.get("lessons")):
        if lesson_date is not None and item.get("date") != lesson_date:
            continue
        if item.get("student") == student or item.get("learner") == student:
            return item
        if isinstance(learner_id, str) and item.get("learner_id") == learner_id:
            return item
    return None


def _find_class(
    store: dict[str, JsonValue],
    learner: dict[str, JsonValue] | None,
) -> dict[str, JsonValue] | None:
    if learner is None:
        return None
    class_id = learner.get("class_id")
    if not isinstance(class_id, str):
        return None
    for item in _dict_items(store.get("classes")):
        if item.get("id") == class_id or item.get("class_id") == class_id:
            return item
    return None


def _learner_id(learner: dict[str, JsonValue] | None) -> str | None:
    if learner is None:
        return None
    canonical_id = learner.get("id")
    if isinstance(canonical_id, str):
        return canonical_id
    legacy_id = learner.get("learner_id")
    return legacy_id if isinstance(legacy_id, str) else None


def _warnings(
    store_warning: str | None,
    learner: dict[str, JsonValue] | None,
    lesson: dict[str, JsonValue] | None,
) -> list[JsonValue]:
    warnings: list[JsonValue] = []
    if store_warning is not None:
        warnings.append({"level": "warning", "message": store_warning})
    if learner is None:
        warnings.append({"level": "warning", "message": "learner record not found"})
    if lesson is None:
        warnings.append({"level": "warning", "message": "lesson record not found"})
    return warnings


def _sections(
    student: str,
    lesson: dict[str, JsonValue] | None,
    learner: dict[str, JsonValue] | None,
    class_item: dict[str, JsonValue] | None,
) -> list[JsonValue]:
    topic = _str_value(lesson, "topic") or "등록된 수업 계획이 없습니다."
    return [
        {"type": "summary", "text": f"{student}: {topic}"},
        {"type": "entity_list", "items": _entity_items(learner, class_item, lesson)},
        {"type": "task_list", "items": _task_items(lesson)},
    ]


def _entity_items(
    learner: dict[str, JsonValue] | None,
    class_item: dict[str, JsonValue] | None,
    lesson: dict[str, JsonValue] | None,
) -> list[JsonValue]:
    items: list[JsonValue] = []
    if learner is not None:
        items.append({"label": "Learner", "value": _str_value(learner, "name") or "가상학생"})
        level = _str_value(learner, "level")
        if level is not None:
            items.append({"label": "Level", "value": level})
    if class_item is not None:
        class_name = _str_value(class_item, "name") or "Synthetic Class"
        items.append({"label": "Class", "value": class_name})
        schedule = _str_value(class_item, "schedule")
        if schedule is not None:
            items.append({"label": "Schedule", "value": schedule})
    if lesson is not None:
        materials = _list_strings(lesson.get("materials"))
        if materials:
            items.append({"label": "Materials", "value": ", ".join(materials)})
    return items


def _task_items(lesson: dict[str, JsonValue] | None) -> list[JsonValue]:
    if lesson is None:
        return []
    items: list[JsonValue] = [
        {"label": task, "status": "planned"} for task in _list_strings(lesson.get("tasks"))
    ]
    homework = _str_value(lesson, "homework")
    if homework is not None:
        items.append({"label": homework, "status": "homework"})
    return items


def _dict_items(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_strings(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _str_value(mapping: dict[str, JsonValue] | None, key: str) -> str | None:
    if mapping is None:
        return None
    value = mapping.get(key)
    return value if isinstance(value, str) else None
