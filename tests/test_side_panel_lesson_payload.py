from __future__ import annotations

import json
from pathlib import Path

from chat_lms_agent.academy_db import store_path
from chat_lms_agent.side_panel_lesson import lesson_panel_payload
from chat_lms_agent.side_panel_validation import side_panel_payload_validate
from chat_lms_agent.state import JsonValue, ProfileState


def test_lesson_panel_payload_declares_empty_sections_when_store_missing(
    tmp_path: Path,
) -> None:
    # Given: a profile with no academy store.
    profile = _profile_state(tmp_path)

    # When: a lesson panel payload is built for a learner.
    payload = lesson_panel_payload(profile, "가상학생", "2026-06-12")

    # Then: the payload is a valid production payload with empty-state sections.
    assert payload["view_id"] == "lesson_prep"
    assert payload["entity_ref"] == "learner:가상학생"
    assert payload["privacy_level"] == "learner"
    assert payload["source_commands"] == [
        {
            "query_name": "academy-db-inspect",
            "command": "academy-db inspect --profile-root <profile-root> --json",
        },
        {
            "query_name": "academy-db-query-list",
            "command": "academy-db query list --profile-root <profile-root> --json",
        },
    ]
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert warnings
    assert _section(payload, "entity_list")["items"] == []
    assert _section(payload, "task_list")["items"] == []
    assert _validate_payload(tmp_path, payload) == 0


def test_lesson_panel_payload_uses_populated_academy_store(tmp_path: Path) -> None:
    # Given: a profile academy store with one learner, class, and dated lesson.
    profile = _profile_state(tmp_path)
    _write_store(
        profile,
        {
            "schema_version": "academy-v1",
            "classes": [
                {
                    "id": "class-1",
                    "name": "Synthetic Class",
                    "schedule": "Friday 18:00",
                },
            ],
            "learners": [
                {
                    "id": "learner-1",
                    "name": "가상학생",
                    "class_id": "class-1",
                    "level": "A2",
                },
            ],
            "lessons": [
                {
                    "id": "lesson-1",
                    "learner_id": "learner-1",
                    "student": "가상학생",
                    "date": "2026-06-12",
                    "topic": "Past tense review",
                    "homework": "Workbook p. 12",
                    "tasks": ["Review irregular verbs", "Check homework"],
                    "materials": ["Unit 4 handout"],
                },
            ],
        },
    )

    # When: the lesson panel payload is built for that learner and date.
    payload = lesson_panel_payload(profile, "가상학생", "2026-06-12")

    # Then: sections carry the store data and still validate.
    assert "Past tense review" in _section(payload, "summary")["text"]
    entity_items = _section(payload, "entity_list")["items"]
    task_items = _section(payload, "task_list")["items"]
    assert isinstance(entity_items, list)
    assert isinstance(task_items, list)
    assert any("Synthetic Class" in json.dumps(item, ensure_ascii=False) for item in entity_items)
    assert any(
        "Review irregular verbs" in json.dumps(item, ensure_ascii=False) for item in task_items
    )
    assert _validate_payload(tmp_path, payload) == 0


def test_lesson_panel_payload_never_raises_for_bad_or_partial_store(tmp_path: Path) -> None:
    # Given: malformed and partial store states that can appear in a private profile.
    profile = _profile_state(tmp_path)
    path = store_path(profile)
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    # When/Then: malformed JSON yields a valid warning payload, not an exception.
    malformed_payload = lesson_panel_payload(profile, "가상학생", None)
    assert _validate_payload(tmp_path, malformed_payload) == 0
    assert malformed_payload["warnings"]

    # When/Then: a partial store also yields a valid warning payload.
    _write_store(profile, {"schema_version": "academy-v1", "learners": [{"name": "가상학생"}]})
    partial_payload = lesson_panel_payload(profile, "가상학생", None)
    assert _validate_payload(tmp_path, partial_payload) == 0
    assert partial_payload["warnings"]


def _section(payload: dict[str, JsonValue], section_type: str) -> dict[str, JsonValue]:
    sections = payload["sections"]
    assert isinstance(sections, list)
    for section in sections:
        assert isinstance(section, dict)
        if section.get("type") == section_type:
            return section
    message = f"missing section: {section_type}"
    raise AssertionError(message)


def _validate_payload(tmp_path: Path, payload: dict[str, JsonValue]) -> int:
    payload_path = tmp_path / "lesson-panel-payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    code, result = side_panel_payload_validate(payload_path)
    assert result["status"] == "PASS"
    return code


def _write_store(profile: ProfileState, payload: dict[str, JsonValue]) -> None:
    path = store_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _profile_state(profile_root: Path) -> ProfileState:
    return ProfileState(root=profile_root.resolve(), repo_root=Path(__file__).resolve().parents[1])
