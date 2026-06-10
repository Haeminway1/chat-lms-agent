from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent.approval_handlers import handle_approval

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
    revived_code, revived_payload = approve_interactively(
        profile_root,
        approval_id,
        "human:owner",
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
    assert revived_code == 2
    assert revived_payload["error_code"] == "APPROVAL_CONSUMED"
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


class FakeTtyStdin:
    """Stand-in for a real teacher terminal in handler-level tests."""

    def __init__(self, line: str) -> None:
        """Queue the single confirmation line a teacher would type."""
        self._line = line

    def isatty(self) -> bool:
        """Report an interactive terminal."""
        return True

    def readline(self) -> str:
        """Return the queued confirmation line."""
        return self._line


def approve_interactively(
    profile_root: Path,
    approval_id: str,
    actor: str,
    *,
    confirm: str | None = None,
) -> tuple[int, dict[str, JsonValue]]:
    args = [
        "approval",
        "approve",
        "--profile-root",
        str(profile_root),
        "--approval-id",
        approval_id,
        "--actor",
        actor,
        "--json",
    ]
    typed = confirm if confirm is not None else approval_id
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        code = handle_approval(args, repo_root(), stdin=FakeTtyStdin(typed + "\n"))
    return code, parse_json_mapping(buffer.getvalue())


def create_planned_approval(tmp_path: Path) -> tuple[str, Path]:
    import_path = tmp_path / "incoming-import.json"
    _ = import_path.write_text(
        json.dumps(
            {
                "schema_version": "academy-import-v1",
                "operation": "upsert_learners",
                "learners": [{"display_name": "Test Learner", "class": "A"}],
            },
        ),
        encoding="utf-8",
    )
    init_result = run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    assert init_result.returncode == 0, init_result.stderr
    needs_approval = run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(import_path),
        "--json",
    )
    assert needs_approval.returncode == 3, needs_approval.stderr
    approval_id = parse_json_mapping(needs_approval.stdout)["approval_id"]
    assert isinstance(approval_id, str)
    return approval_id, import_path


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
        input="",
    )
