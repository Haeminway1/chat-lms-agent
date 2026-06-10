from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.trace_audit_approval_support import create_planned_approval


def test_closeout_blocks_academy_db_schema_change_without_decision(tmp_path: Path) -> None:
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    closeout_result = _run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert closeout_result.returncode == 5
    payload = json.loads(closeout_result.stdout)
    assert payload["missing_memory"] == ["decision:academy-db-schema", "schema:academy-db"]


def test_closeout_passes_after_academy_db_memory_draft_is_applied(tmp_path: Path) -> None:
    draft_path = tmp_path / "memory.json"
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    draft_result = _run_cli(
        "memory",
        "draft",
        "--profile-root",
        str(tmp_path),
        "--for",
        "academy-db-init",
        "--out",
        str(draft_path),
        "--json",
    )
    apply_result = _run_cli(
        "memory",
        "apply-draft",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(draft_path),
        "--json",
    )
    closeout_result = _run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert draft_result.returncode == 0, draft_result.stderr
    assert apply_result.returncode == 0, apply_result.stderr
    assert closeout_result.returncode == 0, closeout_result.stdout
    assert json.loads(closeout_result.stdout)["status"] == "PASS"


def test_blocked_payload_carries_decision_and_reason(tmp_path: Path) -> None:
    # Given: an academy DB change whose memory obligations are unrecorded.
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    assert init_result.returncode == 0, init_result.stderr

    # When: the session tries to close.
    closeout = _run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    # Then: the native continuation contract and a Korean remediation are emitted.
    assert closeout.returncode == 5
    payload = json.loads(closeout.stdout)
    assert payload["decision"] == "block"
    reason = payload["reason"]
    assert isinstance(reason, str)
    assert "memory upsert --key decision:academy-db-schema" in reason
    assert "memory upsert --key schema:academy-db" in reason


def test_blocked_reason_embeds_approval_remediation(tmp_path: Path) -> None:
    # Given: a planned approval only the teacher can resolve.
    approval_id, _ = create_planned_approval(tmp_path)

    # When: the session tries to close.
    closeout = _run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    # Then: the reason names the approval and the exact human command.
    assert closeout.returncode == 5
    payload = json.loads(closeout.stdout)
    assert payload["decision"] == "block"
    reason = payload["reason"]
    assert isinstance(reason, str)
    assert approval_id in reason
    assert f"approval approve --approval-id {approval_id}" in reason
    assert "교사" in reason


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
