from __future__ import annotations

import json
from pathlib import Path

from chat_lms_agent.record_types import load_record_types
from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState


def test_repo_record_type_defaults_load() -> None:
    # Given: the repository default record-type registry.

    # When: record types load without a profile override directory.
    record_types, warnings = load_record_types(_repo_root(), None)

    # Then: teacher-approved attendance and journal defaults are available.
    by_id = {record_type.type_id: record_type for record_type in record_types}
    assert warnings == []
    assert set(by_id) >= {"attendance", "journal"}
    attendance = by_id["attendance"]
    assert attendance.label == "출결"
    assert attendance.source == "repo"
    assert attendance.target == "learner"
    assert [(field.name, field.field_type, field.required) for field in attendance.fields] == [
        ("date", "date", True),
        ("status", "enum", True),
        ("note", "text", False),
    ]
    assert attendance.fields[1].options == ("출석", "결석", "지각", "조퇴", "보강")
    journal = by_id["journal"]
    assert journal.label == "일지"
    assert journal.fields[1].options == ("완료", "부분완료", "미완료")


def test_profile_record_type_overrides_repo_by_id(tmp_path: Path) -> None:
    # Given: a profile-level attendance definition with the same id as the repo default.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_record_type(
        profile.root,
        "attendance.json",
        _record_type_payload(
            record_type_id="attendance",
            label="출결 커스텀",
            fields=[
                {"name": "date", "type": "date", "required": True},
                {
                    "name": "status",
                    "type": "enum",
                    "required": True,
                    "options": ["출석", "결석"],
                },
            ],
        ),
    )

    # When: repo and profile registries load together.
    record_types, warnings = load_record_types(_repo_root(), profile)

    # Then: the profile version wins by id while other repo defaults remain.
    by_id = {record_type.type_id: record_type for record_type in record_types}
    assert warnings == []
    assert by_id["attendance"].source == "profile"
    assert by_id["attendance"].label == "출결 커스텀"
    assert by_id["attendance"].fields[1].options == ("출석", "결석")
    assert by_id["journal"].source == "repo"


def test_malformed_record_type_warns_and_others_still_load(tmp_path: Path) -> None:
    # Given: one valid profile record type and one malformed JSON file.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_record_type(
        profile.root,
        "participation.json",
        _record_type_payload(record_type_id="participation", label="참여도"),
    )
    broken_path = profile.root / STATE_DIR / "record-types" / "broken.json"
    broken_path.write_text("{not json", encoding="utf-8")

    # When: the registry is discovered.
    record_types, warnings = load_record_types(_repo_root(), profile)

    # Then: the malformed file is reported and skipped without aborting discovery.
    by_id = {record_type.type_id for record_type in record_types}
    assert "participation" in by_id
    assert "attendance" in by_id
    assert warnings == ["broken.json: INVALID_JSON"]


def test_record_type_schema_validation_returns_typed_warnings(tmp_path: Path) -> None:
    # Given: profile files with invalid record-type-v1 schema details.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_record_type(
        profile.root,
        "bad-field.json",
        _record_type_payload(
            record_type_id="bad-field",
            label="잘못된 필드",
            fields=[{"name": "score", "type": "json"}],
        ),
    )
    _write_record_type(
        profile.root,
        "enum-options.json",
        _record_type_payload(
            record_type_id="enum-options",
            label="빈 열거형",
            fields=[{"name": "status", "type": "enum", "options": []}],
        ),
    )
    _write_record_type(
        profile.root,
        "missing-id.json",
        {
            "schema_version": "record-type-v1",
            "label": "아이디 없음",
            "target": "learner",
            "fields": [{"name": "date", "type": "date"}],
        },
    )

    # When: invalid files are loaded alongside repo defaults.
    record_types, warnings = load_record_types(_repo_root(), profile)

    # Then: each invalid file yields a typed warning and is skipped.
    loaded_ids = {record_type.type_id for record_type in record_types}
    assert "bad-field" not in loaded_ids
    assert "enum-options" not in loaded_ids
    assert warnings == [
        "bad-field.json: INVALID_FIELD_TYPE",
        "enum-options.json: ENUM_REQUIRES_OPTIONS",
        "missing-id.json: MISSING_ID",
    ]


def _record_type_payload(
    *,
    record_type_id: str,
    label: str,
    fields: list[dict[str, JsonValue]] | None = None,
) -> dict[str, JsonValue]:
    return {
        "schema_version": "record-type-v1",
        "id": record_type_id,
        "label": label,
        "target": "learner",
        "fields": fields if fields is not None else [{"name": "date", "type": "date"}],
    }


def _write_record_type(root: Path, name: str, payload: dict[str, JsonValue]) -> None:
    record_types_dir = root / STATE_DIR / "record-types"
    record_types_dir.mkdir(parents=True, exist_ok=True)
    (record_types_dir / name).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
