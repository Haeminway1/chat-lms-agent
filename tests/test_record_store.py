from __future__ import annotations

import json
from pathlib import Path

from chat_lms_agent.academy_db import inspect_store, store_path
from chat_lms_agent.record_store import add_record, list_records
from chat_lms_agent.record_types import load_record_types
from chat_lms_agent.record_validation import validate_record_values
from chat_lms_agent.state import ProfileState

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _profile(tmp_path: Path) -> ProfileState:
    return ProfileState(root=tmp_path, repo_root=_REPO_ROOT)


def _seed_store(tmp_path: Path, store: dict[str, object]) -> None:
    path = store_path(_profile(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


def _attendance_type() -> object:
    record_types, _ = load_record_types(_REPO_ROOT, None)
    return next(rt for rt in record_types if rt.type_id == "attendance")


# --- validation truth table ---


def test_validate_good_record_passes() -> None:
    errors = validate_record_values(
        _attendance_type(),
        {"date": "2026-06-13", "status": "지각", "note": "버스 늦음"},
    )
    assert errors == []


def test_validate_missing_required_field() -> None:
    errors = validate_record_values(_attendance_type(), {"date": "2026-06-13"})
    assert any("status" in error for error in errors)


def test_validate_enum_not_in_options() -> None:
    errors = validate_record_values(
        _attendance_type(),
        {"date": "2026-06-13", "status": "출근"},
    )
    assert any("status" in error for error in errors)


def test_validate_unknown_field() -> None:
    errors = validate_record_values(
        _attendance_type(),
        {"date": "2026-06-13", "status": "출석", "mood": "good"},
    )
    assert any("mood" in error for error in errors)


def test_validate_bad_date_format() -> None:
    errors = validate_record_values(
        _attendance_type(),
        {"date": "6/13", "status": "출석"},
    )
    assert any("date" in error for error in errors)


# --- add / list round-trip ---


def _seed_one_learner(tmp_path: Path) -> None:
    _seed_store(
        tmp_path,
        {
            "schema_version": "academy-v3",
            "classes": [{"id": "c1", "name": "화목반"}],
            "learners": [{"id": "stu1", "name": "가상민준", "class_id": "c1"}],
            "lessons": [],
        },
    )


def test_add_then_list_round_trip(tmp_path: Path) -> None:
    _seed_one_learner(tmp_path)
    profile = _profile(tmp_path)
    code, payload = add_record(
        profile,
        _REPO_ROOT,
        "attendance",
        "가상민준",
        {"date": "2026-06-13", "status": "지각"},
    )
    assert code == 0
    assert payload["status"] == "PASS"
    list_code, list_payload = list_records(profile, "attendance", "가상민준", None)
    assert list_code == 0
    records = list_payload["records"]
    assert isinstance(records, list)
    assert len(records) == 1
    assert records[0]["status"] == "지각"
    assert records[0]["learner_id"] == "stu1"


def test_list_newest_first_and_recent_cap(tmp_path: Path) -> None:
    _seed_one_learner(tmp_path)
    profile = _profile(tmp_path)
    for date in ("2026-06-10", "2026-06-13", "2026-06-11"):
        _code, _payload = add_record(
            profile,
            _REPO_ROOT,
            "attendance",
            "가상민준",
            {"date": date, "status": "출석"},
        )
    _code, payload = list_records(profile, "attendance", "가상민준", 2)
    records = payload["records"]
    assert isinstance(records, list)
    assert [record["date"] for record in records] == ["2026-06-13", "2026-06-11"]


def test_learner_resolved_by_id_and_name(tmp_path: Path) -> None:
    _seed_one_learner(tmp_path)
    profile = _profile(tmp_path)
    for ref in ("가상민준", "stu1"):
        code, _payload = add_record(
            profile,
            _REPO_ROOT,
            "attendance",
            ref,
            {"date": "2026-06-13", "status": "출석"},
        )
        assert code == 0
    _code, payload = list_records(profile, "attendance", "stu1", None)
    assert payload["count"] == 2


def test_unknown_type_rejected(tmp_path: Path) -> None:
    _seed_one_learner(tmp_path)
    code, payload = add_record(
        _profile(tmp_path),
        _REPO_ROOT,
        "nope",
        "가상민준",
        {"date": "2026-06-13"},
    )
    assert code == 2
    assert payload["error_code"] == "UNKNOWN_RECORD_TYPE"


def test_unresolvable_learner_rejected(tmp_path: Path) -> None:
    _seed_one_learner(tmp_path)
    code, payload = add_record(
        _profile(tmp_path),
        _REPO_ROOT,
        "attendance",
        "없는학생",
        {"date": "2026-06-13", "status": "출석"},
    )
    assert code == 2
    assert payload["error_code"] == "UNRESOLVABLE_LEARNER"


def test_invalid_record_rejected_before_write(tmp_path: Path) -> None:
    _seed_one_learner(tmp_path)
    profile = _profile(tmp_path)
    code, payload = add_record(
        profile,
        _REPO_ROOT,
        "attendance",
        "가상민준",
        {"date": "2026-06-13", "status": "출근"},
    )
    assert code == 2
    assert payload["error_code"] == "INVALID_RECORD"
    _code, list_payload = list_records(profile, "attendance", "가상민준", None)
    assert list_payload["count"] == 0


def test_existing_entities_untouched_and_counts_gain_records(tmp_path: Path) -> None:
    _seed_one_learner(tmp_path)
    profile = _profile(tmp_path)
    _code, _payload = add_record(
        profile,
        _REPO_ROOT,
        "attendance",
        "가상민준",
        {"date": "2026-06-13", "status": "출석"},
    )
    raw = json.loads(store_path(profile).read_text(encoding="utf-8-sig"))
    assert len(raw["learners"]) == 1
    assert len(raw["classes"]) == 1
    assert raw["lessons"] == []
    counts = inspect_store(profile)["counts"]
    assert isinstance(counts, dict)
    assert counts["records"] == 1
    assert counts["learners"] == 1
