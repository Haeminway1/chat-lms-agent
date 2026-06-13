from __future__ import annotations

from typing import TYPE_CHECKING

from chat_lms_agent.academy_db_import_normalization import normalize_import_payload

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def test_normalize_import_payload_maps_legacy_ids_to_canonical_ids() -> None:
    # Given: an official import payload using legacy id field names.
    payload: dict[str, JsonValue] = {
        "classes": [{"class_id": "ga-class-alpha", "name": "가상 초등 A"}],
        "learners": [
            {
                "class_id": "ga-class-alpha",
                "learner_id": "ga-learner-001",
                "name": "가상학생 하나",
            },
        ],
        "lessons": [
            {
                "date": "2026-06-13",
                "learner_id": "ga-learner-001",
                "topic": "Past tense",
            },
        ],
    }

    # When: the payload is normalized for storage.
    normalized, warnings = normalize_import_payload(payload)

    # Then: canonical ids are present and no warning is needed.
    assert warnings == []
    classes = _object_list(normalized["classes"])
    learners = _object_list(normalized["learners"])
    assert classes[0]["id"] == "ga-class-alpha"
    assert classes[0]["class_id"] == "ga-class-alpha"
    assert learners[0]["id"] == "ga-learner-001"
    assert learners[0]["learner_id"] == "ga-learner-001"


def test_normalize_import_payload_derives_name_from_display_name() -> None:
    # Given: a legacy import learner that uses display_name.
    payload: dict[str, JsonValue] = {
        "learners": [{"learner_id": "ga-learner-002", "display_name": "가상학생 둘"}],
    }

    # When: the payload is normalized for the lesson panel contract.
    normalized, warnings = normalize_import_payload(payload)

    # Then: display_name becomes the canonical display name.
    assert warnings == []
    learners = _object_list(normalized["learners"])
    assert learners[0]["id"] == "ga-learner-002"
    assert learners[0]["name"] == "가상학생 둘"
    assert learners[0]["display_name"] == "가상학생 둘"


def test_normalize_import_payload_reports_learner_name_missing_by_id() -> None:
    # Given: two legacy learners without a displayable name.
    payload: dict[str, JsonValue] = {
        "learners": [
            {"learner_id": "ga-missing-001"},
            {"id": "ga-missing-002"},
        ],
    }

    # When: the payload is normalized.
    normalized, warnings = normalize_import_payload(payload)

    # Then: the normalized payload is still returned, with a typed warning listing ids.
    learners = _object_list(normalized["learners"])
    assert learners[0]["id"] == "ga-missing-001"
    assert learners[1]["id"] == "ga-missing-002"
    assert len(warnings) == 1
    warning = warnings[0]
    assert isinstance(warning, dict)
    assert warning["code"] == "LEARNER_NAME_MISSING"
    assert warning["entity"] == "learners"
    assert warning["ids"] == ["ga-missing-001", "ga-missing-002"]
    assert warning["level"] == "warning"


def _object_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]
