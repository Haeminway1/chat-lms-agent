from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.academy_db import store_path
from chat_lms_agent.approvals import approve_request
from chat_lms_agent.side_panel_validation import side_panel_payload_validate
from chat_lms_agent.state import ProfileState

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def apply_synthetic_import(profile_root: Path, profile: ProfileState) -> None:
    source_path = synthetic_source_path()
    first = run_cli(
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
    approval_id = json_payload(first.stdout)["approval_id"]
    assert isinstance(approval_id, str)
    code, approval = approve_request(profile, approval_id, "teacher")
    assert code == 0
    assert approval["approval_status"] == "APPROVED"
    second = run_cli(
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


def assert_imported_store_has_canonical_ids(profile: ProfileState) -> None:
    store = json_payload(store_path(profile).read_text(encoding="utf-8"))
    learners = object_list(store["learners"])
    classes = object_list(store["classes"])
    assert learners[0]["id"] == "ga-learner-001"
    assert classes[0]["id"] == "ga-class-alpha"


def write_store(profile: ProfileState, payload: dict[str, JsonValue]) -> None:
    path = store_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def section_text(payload: dict[str, JsonValue], section_type: str) -> str:
    section = section_payload(payload, section_type)
    text = section.get("text")
    return text if isinstance(text, str) else ""


def assert_section_contains(
    payload: dict[str, JsonValue],
    section_type: str,
    expected_texts: tuple[str, ...],
) -> None:
    section_blob = json.dumps(section_payload(payload, section_type), ensure_ascii=False)
    for expected_text in expected_texts:
        assert expected_text in section_blob


def section_payload(payload: dict[str, JsonValue], section_type: str) -> dict[str, JsonValue]:
    sections = payload["sections"]
    assert isinstance(sections, list)
    for section in sections:
        assert isinstance(section, dict)
        if section.get("type") == section_type:
            return section
    message = f"missing section: {section_type}"
    raise AssertionError(message)


def warning_messages(payload: dict[str, JsonValue]) -> list[str]:
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    messages: list[str] = []
    for warning in warnings:
        if isinstance(warning, dict):
            message = warning.get("message")
            if isinstance(message, str):
                messages.append(message)
    return messages


def warning_by_code(payload: dict[str, JsonValue], code: str) -> dict[str, JsonValue]:
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    for warning in warnings:
        assert isinstance(warning, dict)
        if warning.get("code") == code:
            return warning
    message = f"missing warning: {code}"
    raise AssertionError(message)


def field_payload(fields: dict[str, JsonValue], entity: str, name: str) -> JsonValue:
    entity_fields = fields[entity]
    assert isinstance(entity_fields, dict)
    return entity_fields[name]


def validate_payload(tmp_path: Path, payload: dict[str, JsonValue]) -> int:
    payload_path = tmp_path / "lesson-panel-payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    code, result = side_panel_payload_validate(payload_path)
    assert result["status"] == "PASS"
    return code


def json_payload(raw: str) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


def object_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]


def profile_state(profile_root: Path) -> ProfileState:
    return ProfileState(root=profile_root.resolve(), repo_root=repo_root())


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def synthetic_source_path() -> Path:
    return repo_root() / "tests" / "fixtures" / "academy_db" / "synthetic_academy.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root(),
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )


def http_json(port: int, path: str) -> dict[str, JsonValue]:
    connection = HTTPConnection("127.0.0.1", port, timeout=2.0)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 200
        return json_payload(response.read().decode("utf-8"))
    finally:
        connection.close()


def poll_json(port: int, path: str) -> dict[str, JsonValue]:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            return http_json(port, path)
        except (AssertionError, ConnectionError, OSError):
            time.sleep(0.1)
    message = "server did not become ready"
    raise AssertionError(message)


def unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def stop_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _ = process.communicate(timeout=5)
