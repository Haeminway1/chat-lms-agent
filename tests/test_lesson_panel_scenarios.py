from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypedDict, assert_never
from urllib.parse import urlencode

import pytest

from chat_lms_agent.academy_db import schema_payload, store_path
from chat_lms_agent.approvals import approve_request
from chat_lms_agent.side_panel_lesson import lesson_panel_payload
from chat_lms_agent.side_panel_validation import side_panel_payload_validate
from chat_lms_agent.state import ProfileState

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

TODAY: Final = "2026-06-13"
OTHER_DAY: Final = "2026-06-12"


class ScenarioCase(TypedDict):
    case_id: str
    mode: Literal["store", "import"]
    student: str
    lesson_date: str
    store: dict[str, JsonValue]
    summary: str
    entity_texts: tuple[str, ...]
    task_texts: tuple[str, ...]
    warnings: tuple[str, ...]
    forbidden_warnings: tuple[str, ...]


@pytest.mark.parametrize(
    "case_id",
    [
        "learner-with-lesson-today",
        "new-learner-no-lessons",
        "multiple-learners-same-date",
        "unknown-student-typo",
        "import-apply-then-panel-populated",
    ],
)
def test_lesson_panel_dogfood_scenario_matrix(tmp_path: Path, case_id: str) -> None:
    # Given: a synthetic academy store prepared by the scenario's real data path.
    case = _scenario_case(case_id)
    profile = _profile_state(tmp_path)
    match case["mode"]:
        case "store":
            _write_store(profile, case["store"])
        case "import":
            _apply_synthetic_import(tmp_path, profile)
            _assert_imported_store_has_canonical_ids(profile)
        case unreachable:
            assert_never(unreachable)

    # When: the lesson panel payload is built for the requested learner/date.
    payload = lesson_panel_payload(profile, case["student"], case["lesson_date"])

    # Then: the typed payload matches the scenario outcome and validates.
    assert _validate_payload(tmp_path, payload) == 0
    assert case["summary"] in _section_text(payload, "summary")
    _assert_section_contains(payload, "entity_list", case["entity_texts"])
    _assert_section_contains(payload, "task_list", case["task_texts"])
    messages = _warning_messages(payload)
    for expected_warning in case["warnings"]:
        assert any(expected_warning in message for message in messages)
    for forbidden_warning in case["forbidden_warnings"]:
        assert all(forbidden_warning not in message for message in messages)


def test_synthetic_academy_fixture_is_public_safe_and_virtual_named() -> None:
    # Given/When: the shared synthetic academy fixture is read from the public repo.
    fixture = _json_payload(_synthetic_source_path().read_text(encoding="utf-8"))

    # Then: it is public-safe and contains only 가상 learner display names.
    assert fixture["public_safe"] is True
    learners = _object_list(fixture["learners"])
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
    assert _field(fields, "learners", "id") == {"required": True, "type": "string"}
    assert _field(fields, "learners", "name") == {"required": True, "type": "string"}
    assert _field(fields, "learners", "class_id") == {"required": False, "type": "string"}
    assert _field(fields, "classes", "id") == {"required": True, "type": "string"}
    assert _field(fields, "classes", "name") == {"required": True, "type": "string"}
    assert _field(fields, "lessons", "date") == {"required": True, "type": "string"}
    assert _field(fields, "lessons", "learner_id") == {"required": False, "type": "string"}
    assert _field(fields, "lessons", "student") == {"required": False, "type": "string"}


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
    result = _run_cli(
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
    payload = _json_payload(result.stdout)
    warning = _warning_by_code(payload, "LEARNER_NAME_MISSING")
    assert warning["level"] == "warning"
    assert warning["entity"] == "learners"
    assert warning["ids"] == ["ga-missing-name"]


def test_lesson_panel_reads_preexisting_legacy_store_by_learner_id(tmp_path: Path) -> None:
    # Given: a pre-normalization store that only has legacy learner/class ids.
    profile = _profile_state(tmp_path)
    _write_store(profile, _legacy_store_without_canonical_ids())

    # When: the panel is requested with the legacy learner id.
    payload = lesson_panel_payload(profile, "ga-legacy-001", TODAY)

    # Then: the existing store still renders populated sections without not-found warnings.
    assert _validate_payload(tmp_path, payload) == 0
    assert "Legacy linked topic" in _section_text(payload, "summary")
    _assert_section_contains(payload, "entity_list", ("가상학생 레거시", "가상 레거시반"))
    _assert_section_contains(payload, "task_list", ("Legacy task", "Legacy homework"))
    assert all("not found" not in message for message in _warning_messages(payload))


def test_lesson_server_e2e_renders_populated_synthetic_import(tmp_path: Path) -> None:
    # Given: installed lesson assets and a synthetic import applied through approval.
    profile_root = tmp_path / "profile"
    profile = _profile_state(profile_root)
    install = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    assert install.returncode == 0, install.stderr
    _apply_synthetic_import(profile_root, profile)
    port = _unused_tcp_port()
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
        _ = _poll_json(port, "/api/health")
        params = urlencode({"student": "가상학생 하나", "date": TODAY})
        payload = _http_json(port, f"/api/lesson-panel?{params}")
    finally:
        _stop_process(process)

    # Then: the HTTP surface returns populated typed JSON with no not-found warnings.
    assert payload["view_id"] == "lesson_prep"
    assert "Past tense travel stories" in _section_text(payload, "summary")
    _assert_section_contains(payload, "entity_list", ("가상학생 하나", "가상 초등 A"))
    _assert_section_contains(payload, "task_list", ("Review past tense", "Workbook p. 18"))
    assert all("not found" not in message for message in _warning_messages(payload))


def _scenario_cases() -> tuple[ScenarioCase, ...]:
    return (
        {
            "case_id": "learner-with-lesson-today",
            "mode": "store",
            "student": "가상학생 하나",
            "lesson_date": TODAY,
            "store": _canonical_store(),
            "summary": "Past tense travel stories",
            "entity_texts": ("가상학생 하나", "A2", "가상 초등 A", "Unit 4 handout"),
            "task_texts": ("Review past tense", "Workbook p. 18"),
            "warnings": (),
            "forbidden_warnings": ("not found",),
        },
        {
            "case_id": "new-learner-no-lessons",
            "mode": "store",
            "student": "가상학생 신규",
            "lesson_date": TODAY,
            "store": _new_learner_store(),
            "summary": "등록된 수업 계획이 없습니다.",
            "entity_texts": ("가상학생 신규", "A1", "가상 초등 A"),
            "task_texts": (),
            "warnings": ("lesson record not found",),
            "forbidden_warnings": ("learner record not found",),
        },
        {
            "case_id": "multiple-learners-same-date",
            "mode": "store",
            "student": "가상학생 둘",
            "lesson_date": TODAY,
            "store": _canonical_store(),
            "summary": "Comparatives and superlatives",
            "entity_texts": ("가상학생 둘", "B1", "가상 초등 A", "Comparison chart"),
            "task_texts": ("Compare city pictures", "Record three comparison sentences"),
            "warnings": (),
            "forbidden_warnings": ("Past tense travel stories", "not found"),
        },
        {
            "case_id": "unknown-student-typo",
            "mode": "store",
            "student": "가상학생 오타",
            "lesson_date": TODAY,
            "store": _canonical_store(),
            "summary": "등록된 수업 계획이 없습니다.",
            "entity_texts": (),
            "task_texts": (),
            "warnings": ("learner record not found", "lesson record not found"),
            "forbidden_warnings": (),
        },
        {
            "case_id": "import-apply-then-panel-populated",
            "mode": "import",
            "student": "가상학생 하나",
            "lesson_date": TODAY,
            "store": {},
            "summary": "Past tense travel stories",
            "entity_texts": ("가상학생 하나", "A2", "가상 초등 A", "Unit 4 handout"),
            "task_texts": ("Review past tense", "Workbook p. 18"),
            "warnings": (),
            "forbidden_warnings": ("not found",),
        },
    )


def _scenario_case(case_id: str) -> ScenarioCase:
    for case in _scenario_cases():
        if case["case_id"] == case_id:
            return case
    message = f"missing scenario case: {case_id}"
    raise AssertionError(message)


def _canonical_store() -> dict[str, JsonValue]:
    return {
        "schema_version": "academy-v3",
        "classes": [
            {
                "id": "ga-class-alpha",
                "name": "가상 초등 A",
                "schedule": "Saturday 10:00",
            },
        ],
        "learners": [
            {
                "class_id": "ga-class-alpha",
                "id": "ga-learner-001",
                "level": "A2",
                "name": "가상학생 하나",
            },
            {
                "class_id": "ga-class-alpha",
                "id": "ga-learner-002",
                "level": "B1",
                "name": "가상학생 둘",
            },
        ],
        "lessons": [
            {
                "date": TODAY,
                "homework": "Workbook p. 18",
                "learner_id": "ga-learner-001",
                "materials": ["Unit 4 handout", "Picture cards"],
                "tasks": ["Review past tense", "Role-play travel plans"],
                "topic": "Past tense travel stories",
            },
            {
                "date": TODAY,
                "homework": "Record three comparison sentences",
                "learner_id": "ga-learner-002",
                "materials": ["Comparison chart"],
                "tasks": ["Compare city pictures", "Correct comparative forms"],
                "topic": "Comparatives and superlatives",
            },
            {"date": OTHER_DAY, "learner_id": "ga-learner-001", "topic": "Older lesson"},
        ],
    }


def _new_learner_store() -> dict[str, JsonValue]:
    store = _canonical_store()
    learners = _object_list(store["learners"])
    learners.append(
        {
            "class_id": "ga-class-alpha",
            "id": "ga-learner-new",
            "level": "A1",
            "name": "가상학생 신규",
        },
    )
    store["learners"] = learners
    return store


def _legacy_store_without_canonical_ids() -> dict[str, JsonValue]:
    return {
        "schema_version": "academy-v3",
        "classes": [
            {
                "class_id": "ga-legacy-class",
                "name": "가상 레거시반",
                "schedule": "Saturday 16:00",
            },
        ],
        "learners": [
            {
                "class_id": "ga-legacy-class",
                "learner_id": "ga-legacy-001",
                "level": "B1",
                "name": "가상학생 레거시",
            },
        ],
        "lessons": [
            {
                "date": TODAY,
                "homework": "Legacy homework",
                "learner_id": "ga-legacy-001",
                "materials": ["Legacy material"],
                "tasks": ["Legacy task"],
                "topic": "Legacy linked topic",
            },
        ],
    }


def _apply_synthetic_import(profile_root: Path, profile: ProfileState) -> None:
    source_path = _synthetic_source_path()
    first = _run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(profile_root),
        "--from",
        str(source_path),
        "--json",
    )
    assert first.returncode == 3, first.stderr
    approval_id = _json_payload(first.stdout)["approval_id"]
    assert isinstance(approval_id, str)
    code, approval = approve_request(profile, approval_id, "teacher")
    assert code == 0
    assert approval["approval_status"] == "APPROVED"
    second = _run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(profile_root),
        "--from",
        str(source_path),
        "--approval-id",
        approval_id,
        "--json",
    )
    assert second.returncode == 0, second.stderr


def _assert_imported_store_has_canonical_ids(profile: ProfileState) -> None:
    store = _json_payload(store_path(profile).read_text(encoding="utf-8"))
    learners = _object_list(store["learners"])
    classes = _object_list(store["classes"])
    assert learners[0]["id"] == "ga-learner-001"
    assert classes[0]["id"] == "ga-class-alpha"


def _write_store(profile: ProfileState, payload: dict[str, JsonValue]) -> None:
    path = store_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _section_text(payload: dict[str, JsonValue], section_type: str) -> str:
    section = _section(payload, section_type)
    text = section.get("text")
    return text if isinstance(text, str) else ""


def _assert_section_contains(
    payload: dict[str, JsonValue],
    section_type: str,
    expected_texts: tuple[str, ...],
) -> None:
    section_text = json.dumps(_section(payload, section_type), ensure_ascii=False)
    for expected_text in expected_texts:
        assert expected_text in section_text


def _section(payload: dict[str, JsonValue], section_type: str) -> dict[str, JsonValue]:
    sections = payload["sections"]
    assert isinstance(sections, list)
    for section in sections:
        assert isinstance(section, dict)
        if section.get("type") == section_type:
            return section
    message = f"missing section: {section_type}"
    raise AssertionError(message)


def _warning_messages(payload: dict[str, JsonValue]) -> list[str]:
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    messages: list[str] = []
    for warning in warnings:
        if isinstance(warning, dict):
            message = warning.get("message")
            if isinstance(message, str):
                messages.append(message)
    return messages


def _warning_by_code(payload: dict[str, JsonValue], code: str) -> dict[str, JsonValue]:
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    for warning in warnings:
        assert isinstance(warning, dict)
        if warning.get("code") == code:
            return warning
    message = f"missing warning: {code}"
    raise AssertionError(message)


def _field(fields: dict[str, JsonValue], entity: str, name: str) -> JsonValue:
    entity_fields = fields[entity]
    assert isinstance(entity_fields, dict)
    return entity_fields[name]


def _validate_payload(tmp_path: Path, payload: dict[str, JsonValue]) -> int:
    payload_path = tmp_path / "lesson-panel-payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    code, result = side_panel_payload_validate(payload_path)
    assert result["status"] == "PASS"
    return code


def _json_payload(raw: str) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


def _object_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]


def _profile_state(profile_root: Path) -> ProfileState:
    return ProfileState(root=profile_root.resolve(), repo_root=_repo_root())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _synthetic_source_path() -> Path:
    return _repo_root() / "tests" / "fixtures" / "academy_db" / "synthetic_academy.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )


def _http_json(port: int, path: str) -> dict[str, JsonValue]:
    connection = HTTPConnection("127.0.0.1", port, timeout=2.0)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 200
        return _json_payload(response.read().decode("utf-8"))
    finally:
        connection.close()


def _poll_json(port: int, path: str) -> dict[str, JsonValue]:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            return _http_json(port, path)
        except (AssertionError, ConnectionError, OSError):
            time.sleep(0.1)
    message = "server did not become ready"
    raise AssertionError(message)


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _ = process.communicate(timeout=5)
