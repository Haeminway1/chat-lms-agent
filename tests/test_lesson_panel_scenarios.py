from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, assert_never
from urllib.parse import urlencode

import pytest

from chat_lms_agent.academy_db import schema_payload
from chat_lms_agent.side_panel_lesson import lesson_panel_payload
from tests.lesson_panel_scenario_data import (
    CASE_IDS,
    TODAY,
    legacy_store_without_canonical_ids,
    scenario_case,
)
from tests.lesson_panel_scenario_support import (
    apply_synthetic_import,
    assert_imported_store_has_canonical_ids,
    assert_section_contains,
    field_payload,
    http_json,
    json_payload,
    object_list,
    poll_json,
    profile_state,
    run_cli,
    section_text,
    stop_process,
    synthetic_source_path,
    unused_tcp_port,
    validate_payload,
    warning_by_code,
    warning_messages,
    write_store,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_lesson_panel_dogfood_scenario_matrix(tmp_path: Path, case_id: str) -> None:
    # Given: a synthetic academy store prepared by the scenario's real data path.
    case = scenario_case(case_id)
    profile = profile_state(tmp_path)
    match case["mode"]:
        case "store":
            write_store(profile, case["store"])
        case "import":
            apply_synthetic_import(tmp_path, profile)
            assert_imported_store_has_canonical_ids(profile)
        case unreachable:
            assert_never(unreachable)

    # When: the lesson panel payload is built for the requested learner/date.
    payload = lesson_panel_payload(profile, case["student"], case["lesson_date"])

    # Then: the typed payload matches the scenario outcome and validates.
    assert validate_payload(tmp_path, payload) == 0
    assert case["summary"] in section_text(payload, "summary")
    assert_section_contains(payload, "entity_list", case["entity_texts"])
    assert_section_contains(payload, "task_list", case["task_texts"])
    messages = warning_messages(payload)
    for expected_warning in case["warnings"]:
        assert any(expected_warning in message for message in messages)
    for forbidden_warning in case["forbidden_warnings"]:
        assert all(forbidden_warning not in message for message in messages)


def test_synthetic_academy_fixture_is_public_safe_and_virtual_named() -> None:
    # Given/When: the shared synthetic academy fixture is read from the public repo.
    fixture = json_payload(synthetic_source_path().read_text(encoding="utf-8"))

    # Then: it is public-safe and contains only 가상 learner display names.
    assert fixture["public_safe"] is True
    learners = object_list(fixture["learners"])
    assert len(learners) == 4
    for learner in learners:
        name = learner["name"]
        assert isinstance(name, str)
        assert name.startswith("가상")


def test_academy_schema_payload_pins_entity_field_contract() -> None:
    # Given/When: the public academy schema payload is requested.
    payload = schema_payload()

    # Then: each entity declares its canonical data-binding fields.
    fields = payload["fields"]
    assert isinstance(fields, dict)
    assert field_payload(fields, "learners", "id") == {"required": True, "type": "string"}
    assert field_payload(fields, "learners", "name") == {"required": True, "type": "string"}
    assert field_payload(fields, "classes", "id") == {"required": True, "type": "string"}
    assert field_payload(fields, "classes", "name") == {"required": True, "type": "string"}
    assert field_payload(fields, "lessons", "date") == {"required": True, "type": "string"}
    assert field_payload(fields, "lessons", "learner_id") == {
        "required": False,
        "type": "string",
    }


def test_academy_import_plan_warns_when_legacy_learner_has_no_name(tmp_path: Path) -> None:
    # Given: an official import-shaped learner without the display name the panel needs.
    source_path = tmp_path / "missing-name-import.json"
    source_path.write_text(
        json.dumps(
            {
                "classes": [{"class_id": "ga-class-missing", "name": "가상 누락반"}],
                "learners": [{"class_id": "ga-class-missing", "learner_id": "ga-missing-name"}],
                "lessons": [],
                "schema_version": "academy-v3",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # When: the teacher asks for an import plan.
    result = run_cli(
        "academy-db",
        "import",
        "plan",
        "--from",
        str(source_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: a typed warning lists the learner ids that would be unrenderable.
    assert result.returncode == 0, result.stderr
    payload = json_payload(result.stdout)
    warning = warning_by_code(payload, "LEARNER_NAME_MISSING")
    assert warning["level"] == "warning"
    assert warning["entity"] == "learners"
    assert warning["ids"] == ["ga-missing-name"]


def test_lesson_panel_reads_preexisting_legacy_store_by_learner_id(tmp_path: Path) -> None:
    # Given: a pre-normalization store that only has legacy learner/class ids.
    profile = profile_state(tmp_path)
    write_store(profile, legacy_store_without_canonical_ids())

    # When: the panel is requested with the legacy learner id.
    payload = lesson_panel_payload(profile, "ga-legacy-001", TODAY)

    # Then: the existing store still renders populated sections without not-found warnings.
    assert validate_payload(tmp_path, payload) == 0
    assert "Legacy linked topic" in section_text(payload, "summary")
    assert_section_contains(payload, "entity_list", ("가상학생 레거시", "가상 레거시반"))
    assert_section_contains(payload, "task_list", ("Legacy task", "Legacy homework"))
    assert all("not found" not in message for message in warning_messages(payload))


def test_lesson_server_e2e_renders_populated_synthetic_import(tmp_path: Path) -> None:
    # Given: installed lesson assets and a synthetic import applied through approval.
    profile_root = tmp_path / "profile"
    profile = profile_state(profile_root)
    install = run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    assert install.returncode == 0, install.stderr
    apply_synthetic_import(profile_root, profile)
    port = unused_tcp_port()
    server_path = profile_root / "codex-workspace" / "scripts" / "lesson_panel_server.py"
    process = subprocess.Popen(
        [sys.executable, str(server_path), "--port", str(port)],
        cwd=server_path.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # When: the installed server is queried through the real HTTP API.
        _ = poll_json(port, "/api/health")
        params = urlencode({"student": "가상학생 하나", "date": TODAY})
        payload = http_json(port, f"/api/lesson-panel?{params}")
    finally:
        stop_process(process)

    # Then: the HTTP surface returns populated typed JSON with no not-found warnings.
    assert payload["view_id"] == "lesson_prep"
    assert "Past tense travel stories" in section_text(payload, "summary")
    assert_section_contains(payload, "entity_list", ("가상학생 하나", "가상 초등 A"))
    assert_section_contains(payload, "task_list", ("Review past tense", "Workbook p. 18"))
    assert all("not found" not in message for message in warning_messages(payload))
