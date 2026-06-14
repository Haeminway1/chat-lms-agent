from __future__ import annotations

import json
from pathlib import Path

from chat_lms_agent.academy_db import store_path
from chat_lms_agent.record_store import add_record
from chat_lms_agent.side_panel_records import records_panel_payload
from chat_lms_agent.side_panel_validation import side_panel_payload_validate
from chat_lms_agent.state import ProfileState

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _profile(tmp_path: Path) -> ProfileState:
    return ProfileState(root=tmp_path, repo_root=_REPO_ROOT)


def _seed_learner(tmp_path: Path) -> None:
    path = store_path(_profile(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    store = {
        "schema_version": "academy-v3",
        "classes": [{"id": "c1", "name": "화목반"}],
        "learners": [{"id": "stu1", "name": "가상민준", "class_id": "c1"}],
        "lessons": [],
    }
    _ = path.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


def _validate(payload: dict[str, object], tmp_path: Path) -> int:
    out = tmp_path / "records_payload.json"
    _ = out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    code, _result = side_panel_payload_validate(out)
    return code


def test_records_payload_populated_is_validator_clean(tmp_path: Path) -> None:
    _seed_learner(tmp_path)
    profile = _profile(tmp_path)
    for date, status in (("2026-06-13", "지각"), ("2026-06-11", "출석")):
        _code, _payload = add_record(
            profile,
            _REPO_ROOT,
            "attendance",
            "가상민준",
            {"date": date, "status": status},
        )
    payload = records_panel_payload(profile, "가상민준", "attendance", None)
    assert payload["view_id"] == "attendance_summary"
    assert payload["warnings"] == []
    sections = payload["sections"]
    assert isinstance(sections, list)
    entity = next(section for section in sections if section["type"] == "entity_list")
    assert isinstance(entity["items"], list)
    assert len(entity["items"]) == 2
    assert entity["items"][0]["label"] == "2026-06-13"
    assert _validate(payload, tmp_path) == 0


def test_records_payload_empty_is_graceful_and_valid(tmp_path: Path) -> None:
    _seed_learner(tmp_path)
    payload = records_panel_payload(_profile(tmp_path), "가상민준", "attendance", None)
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert len(warnings) == 1
    assert _validate(payload, tmp_path) == 0


def test_records_payload_recent_cap(tmp_path: Path) -> None:
    _seed_learner(tmp_path)
    profile = _profile(tmp_path)
    for date in ("2026-06-10", "2026-06-13", "2026-06-11"):
        _code, _payload = add_record(
            profile,
            _REPO_ROOT,
            "attendance",
            "가상민준",
            {"date": date, "status": "출석"},
        )
    payload = records_panel_payload(profile, "가상민준", "attendance", 2)
    sections = payload["sections"]
    assert isinstance(sections, list)
    entity = next(section for section in sections if section["type"] == "entity_list")
    items = entity["items"]
    assert isinstance(items, list)
    assert [item["label"] for item in items] == ["2026-06-13", "2026-06-11"]
