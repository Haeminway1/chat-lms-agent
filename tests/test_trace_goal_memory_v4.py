from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath


def test_trace_export_and_inspect_show_trajectory(tmp_path: Path) -> None:
    # Given: a private trace record written in the current per-record JSON format.
    trace_dir = tmp_path / ".chat-lms-state" / "trace"
    trace_dir.mkdir(parents=True)
    trace_payload = {
        "schema_version": "trace-v1",
        "trace_id": "trace_v4_001",
        "event_type": "command",
        "profile_root": "<profile-root>",
        "summary": "Ran academy DB import.",
        "details": {"command": ["academy-db", "import", "plan"]},
    }
    (trace_dir / "trace_v4_001.json").write_text(
        json.dumps(trace_payload),
        encoding="utf-8",
    )

    # When: exporting and inspecting the trajectory.
    export_result = _run_cli(
        "trace",
        "export",
        "--profile-root",
        str(tmp_path),
        "--format",
        "trajectory",
        "--json",
    )
    inspect_result = _run_cli(
        "trace",
        "inspect",
        "--profile-root",
        str(tmp_path),
        "--id",
        "trace_v4_001",
        "--json",
    )

    # Then: both surfaces explain the run without leaking local paths.
    assert export_result.returncode == 0, export_result.stdout
    assert inspect_result.returncode == 0, inspect_result.stdout
    assert str(tmp_path) not in export_result.stdout
    export_payload = json.loads(export_result.stdout)
    inspect_payload = json.loads(inspect_result.stdout)
    assert export_payload["schema_version"] == "trajectory-v1"
    assert export_payload["trajectory"][0]["trace_id"] == "trace_v4_001"
    assert inspect_payload["trajectory"]["summary"] == "Ran academy DB import."


def test_trace_and_audit_reads_redact_persisted_raw_records(tmp_path: Path) -> None:
    # Given: raw trace and audit records persisted before the read-side redaction pass.
    trace_dir = tmp_path / ".chat-lms-state" / "trace"
    audit_dir = tmp_path / ".chat-lms-state" / "audit"
    trace_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    private_summary = (
        f"raw path {tmp_path} SECRET_TOKEN=hidden "
        "teacher password: hunter2 api secret = open-sesame"
    )
    stale_private_path = "C:\\Users\\haemi\\private-profile\\learner.csv"
    stale_posix_path = str(PurePosixPath("/") / "tmp" / "private-profile" / "learner.csv")
    trace_payload = {
        "schema_version": "trace-v1",
        "trace_id": "trace_leaky_001",
        "event_type": "command",
        "profile_root": str(tmp_path),
        "summary": f"{private_summary} {stale_private_path} {stale_posix_path}",
        "details": {
            "command": [
                "echo",
                str(tmp_path),
                stale_private_path,
                stale_posix_path,
                "SECRET_TOKEN=hidden",
            ],
        },
    }
    audit_payload = {
        "schema_version": "audit-v1",
        "audit_id": "audit_leaky_001",
        "operation": "import",
        "profile_root": str(tmp_path),
        "summary": f"{private_summary} {stale_private_path} {stale_posix_path}",
        "details": {
            "raw_stdout": (
                f"raw stdout: {tmp_path} {stale_private_path} "
                f"{stale_posix_path} SECRET_TOKEN=hidden"
            ),
        },
    }
    (trace_dir / "trace_leaky_001.json").write_text(
        json.dumps(trace_payload),
        encoding="utf-8",
    )
    (audit_dir / "audit_leaky_001.json").write_text(
        json.dumps(audit_payload),
        encoding="utf-8",
    )

    # When: reading the persisted records through public CLI surfaces.
    trace_export = _run_cli(
        "trace",
        "export",
        "--profile-root",
        str(tmp_path),
        "--format",
        "trajectory",
        "--json",
    )
    trace_show = _run_cli(
        "trace",
        "show",
        "--profile-root",
        str(tmp_path),
        "--id",
        "trace_leaky_001",
        "--json",
    )
    audit_list = _run_cli("audit", "list", "--profile-root", str(tmp_path), "--json")

    # Then: read-side outputs are redacted even if stored records were raw.
    assert trace_export.returncode == 0, trace_export.stdout
    assert trace_show.returncode == 0, trace_show.stdout
    assert audit_list.returncode == 0, audit_list.stdout
    for output in (trace_export.stdout, trace_show.stdout, audit_list.stdout):
        assert str(tmp_path) not in output
        assert "SECRET_TOKEN" not in output
        assert "hunter2" not in output
        assert "open-sesame" not in output
        assert "private-profile" not in output
        assert "<profile-root>" in output or "[redacted]" in output


def test_memory_levels_returns_layered_taxonomy() -> None:
    # Given/When: the agent asks for the canonical memory level map.
    result = _run_cli("memory", "levels", "--json")

    # Then: TencentDB-style L0-L3 concepts are mapped into local Chat LMS memory.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == "memory-levels-v1"
    levels = {level["id"]: level for level in payload["levels"]}
    assert levels["conversation_ref"]["hydrated_by_default"] is False
    assert levels["persona_or_policy"]["requires_review"] is True
    assert payload["source_reference"] == "TencentDB-Agent-Memory structural mapping"


def test_goal_verify_blocks_until_evidence_exists(tmp_path: Path) -> None:
    # Given: a goal with no evidence yet.
    status_result = _run_cli("goal", "status", "--profile-root", str(tmp_path), "--json")
    verify_before = _run_cli(
        "goal",
        "verify",
        "--profile-root",
        str(tmp_path),
        "--goal-id",
        "goal_default",
        "--json",
    )
    hollow_evidence_path = tmp_path / "hollow-note.txt"
    hollow_evidence_path.write_text("looks good to me", encoding="utf-8")
    evidence_path = tmp_path / "qa-evidence.txt"
    evidence_path.write_text("pytest passed and tmux scenario passed", encoding="utf-8")

    # When: adding hollow evidence first.
    hollow_add_result = _run_cli(
        "goal",
        "evidence",
        "add",
        "--profile-root",
        str(tmp_path),
        "--goal-id",
        "goal_default",
        "--from",
        str(hollow_evidence_path),
        "--json",
    )
    verify_hollow = _run_cli(
        "goal",
        "verify",
        "--profile-root",
        str(tmp_path),
        "--goal-id",
        "goal_default",
        "--json",
    )

    # And: adding real command/QA evidence afterward.
    add_result = _run_cli(
        "goal",
        "evidence",
        "add",
        "--profile-root",
        str(tmp_path),
        "--goal-id",
        "goal_default",
        "--from",
        str(evidence_path),
        "--json",
    )
    verify_after = _run_cli(
        "goal",
        "verify",
        "--profile-root",
        str(tmp_path),
        "--goal-id",
        "goal_default",
        "--json",
    )

    # Then: the verifier gates completion on evidence refs.
    assert status_result.returncode == 0, status_result.stdout
    assert verify_before.returncode == 5
    verify_before_payload = json.loads(verify_before.stdout)
    assert verify_before_payload["status"] == "BLOCKED"
    assert verify_before_payload["error_code"] == "GOAL_EVIDENCE_MISSING"
    assert hollow_add_result.returncode == 0, hollow_add_result.stdout
    assert verify_hollow.returncode == 5
    verify_hollow_payload = json.loads(verify_hollow.stdout)
    assert verify_hollow_payload["status"] == "BLOCKED"
    assert verify_hollow_payload["error_code"] == "VALID_EVIDENCE_REQUIRED"
    assert add_result.returncode == 0, add_result.stdout
    assert verify_after.returncode == 0, verify_after.stdout
    assert json.loads(verify_after.stdout)["qa_verifier_status"] == "PASS"


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
