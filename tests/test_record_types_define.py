from __future__ import annotations

import json
from typing import TYPE_CHECKING

from chat_lms_agent.academy_db_handlers import handle_academy_db
from chat_lms_agent.record_types import define_record_type, load_record_types
from chat_lms_agent.state import ProfileState

if TYPE_CHECKING:
    from pathlib import Path

from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parents[1]

_VALID: dict[str, object] = {
    "schema_version": "record-type-v1",
    "id": "reading_level",
    "label": "독해 레벨",
    "target": "learner",
    "summary": "주간 독해 레벨 추적",
    "fields": [
        {"name": "date", "type": "date", "required": True, "label": "날짜"},
        {"name": "score", "type": "number", "required": True, "label": "점수"},
    ],
}


def _profile(tmp_path: Path) -> ProfileState:
    return ProfileState(root=tmp_path, repo_root=_REPO_ROOT)


def test_define_writes_profile_record_type(tmp_path: Path) -> None:
    code, payload = define_record_type(_profile(tmp_path), dict(_VALID))
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["id"] == "reading_level"
    record_types, _warnings = load_record_types(_REPO_ROOT, _profile(tmp_path))
    by_id = {record_type.type_id: record_type.source for record_type in record_types}
    assert by_id.get("reading_level") == "profile"


def test_define_rejects_invalid_and_writes_nothing(tmp_path: Path) -> None:
    bad: dict[str, object] = {
        "schema_version": "record-type-v1",
        "id": "",
        "label": "x",
        "target": "learner",
        "fields": [],
    }
    code, payload = define_record_type(_profile(tmp_path), bad)
    assert code == 2
    assert payload["error_code"] == "MISSING_ID"
    record_types, _warnings = load_record_types(_REPO_ROOT, _profile(tmp_path))
    assert all(record_type.type_id != "" for record_type in record_types)


def test_define_overrides_existing_profile_type(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    _code, _payload = define_record_type(profile, dict(_VALID))
    updated = {**_VALID, "label": "독해 레벨 v2"}
    code, _result = define_record_type(profile, updated)
    assert code == 0
    record_types, _warnings = load_record_types(_REPO_ROOT, profile)
    reading = next(rt for rt in record_types if rt.type_id == "reading_level")
    assert reading.label == "독해 레벨 v2"


def test_define_cli_round_trip(tmp_path: Path) -> None:
    answers = tmp_path / "answers.json"
    _ = answers.write_text(json.dumps(_VALID, ensure_ascii=False), encoding="utf-8")
    code = handle_academy_db(
        [
            "academy-db",
            "record-types",
            "define",
            "--from",
            str(answers),
            "--profile-root",
            str(tmp_path),
            "--json",
        ],
        _REPO_ROOT,
    )
    assert code == 0
