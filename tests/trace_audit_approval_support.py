from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def assert_public_output_redacted(output: str, tmp_path: Path) -> None:
    assert str(tmp_path) not in output
    assert "SECRET=" not in output
    assert "top-secret-token" not in output
    assert "raw stdout:" not in output
    assert "Minji Kim" not in output


def assert_private_records_are_redacted(profile_root: Path) -> None:
    state_root = profile_root / ".chat-lms-state"
    trace_files = artifact_files(state_root, "trace")
    audit_files = artifact_files(state_root, "audit")
    assert trace_files, "expected private trace artifact"
    assert audit_files, "expected private audit artifact"

    for record_path in [*trace_files, *audit_files]:
        record_text = record_path.read_text(encoding="utf-8")
        record_payload = parse_json_mapping(record_text)
        assert record_payload["schema_version"]
        assert_public_output_redacted(record_text, profile_root)


def assert_private_audit_retains_planned_and_applied_records(profile_root: Path) -> None:
    audit_payloads = [
        parse_json_mapping(path.read_text(encoding="utf-8"))
        for path in artifact_files(profile_root / ".chat-lms-state", "audit")
    ]
    summaries: set[str] = set()
    for payload in audit_payloads:
        summary = payload.get("summary")
        if isinstance(summary, str):
            summaries.add(summary)
    assert "Academy DB import apply requested approval before writing." in summaries
    assert "Academy DB import applied after human approval." in summaries


def assert_consumed_approval_is_terminal(
    profile_root: Path,
    import_path: Path,
    approval_id: str,
) -> None:
    reopened = run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(profile_root),
        "--from",
        str(import_path),
        "--json",
    )
    revived = run_cli(
        "approval",
        "approve",
        "--profile-root",
        str(profile_root),
        "--approval-id",
        approval_id,
        "--actor",
        "human:owner",
        "--json",
    )
    learner_count = run_cli(
        "academy-db",
        "query",
        "run",
        "--name",
        "learner-count",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    assert reopened.returncode == 2
    assert json.loads(reopened.stdout)["error_code"] == "APPROVAL_CONSUMED"
    assert revived.returncode == 2
    assert json.loads(revived.stdout)["error_code"] == "APPROVAL_CONSUMED"
    assert json.loads(learner_count.stdout)["result"] == 1


def assert_import_plan_stays_applied_after_reuse_rejection(profile_root: Path) -> None:
    plans_path = (
        profile_root
        / ".chat-lms-state"
        / "academy"
        / "imports"
        / "import-plans.json"
    )
    payload = parse_json_mapping(plans_path.read_text(encoding="utf-8"))
    plans = json_object_list(payload["plans"])
    assert isinstance(plans, list)
    statuses: set[str] = set()
    for plan in plans:
        status = plan.get("status")
        if isinstance(status, str):
            statuses.add(status)
    assert statuses == {"APPLIED"}


def artifact_files(state_root: Path, marker: str) -> list[Path]:
    return [
        path
        for path in state_root.rglob("*.json")
        if marker in {part.lower() for part in path.parts}
    ]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_json_mapping(raw: str) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(raw))
    assert isinstance(payload, dict)
    return payload


def json_object_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [cast("dict[str, JsonValue]", item) for item in value if isinstance(item, dict)]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
