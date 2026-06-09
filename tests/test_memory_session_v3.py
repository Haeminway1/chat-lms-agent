from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_memory_compact_creates_hydratable_summary_from_existing_memory(
    tmp_path: Path,
) -> None:
    # Given: existing private-profile memory with detail that should be summarized.
    first_result = _run_cli(
        "memory",
        "upsert",
        "--profile-root",
        str(tmp_path),
        "--key",
        "decision:attendance-policy",
        "--scope",
        "academy-policy",
        "--text",
        "Use attendance CLI checks; private profile is "
        f"{tmp_path}; SECRET_TOKEN=hidden.",
        "--json",
    )
    second_result = _run_cli(
        "memory",
        "upsert",
        "--profile-root",
        str(tmp_path),
        "--key",
        "schema:academy-db",
        "--scope",
        "academy-db",
        "--text",
        "Academy DB initialized through the CLI.",
        "--json",
    )

    # When: compacting memory for the next Codex session.
    compact_result = _run_cli("memory", "compact", "--profile-root", str(tmp_path), "--json")

    # Then: a compact V3 summary is returned without leaking private material.
    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert compact_result.returncode == 0, compact_result.stdout
    payload = json.loads(compact_result.stdout)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == "memory-compact-v1"
    assert payload["profile_root"] == "<profile-root>"
    assert payload["compacted_keys"] == [
        "decision:attendance-policy",
        "schema:academy-db",
    ]
    assert payload["summary"]["hydrated_by_default"] is True
    assert str(tmp_path) not in compact_result.stdout
    assert "SECRET_TOKEN" not in compact_result.stdout


def test_memory_archive_excludes_detail_from_default_context_hydration(
    tmp_path: Path,
) -> None:
    # Given: a memory detail that is useful historically but noisy by default.
    upsert_result = _run_cli(
        "memory",
        "upsert",
        "--profile-root",
        str(tmp_path),
        "--key",
        "decision:legacy-placement-rule",
        "--scope",
        "academy-policy",
        "--text",
        "Legacy placement decision should only be recovered explicitly.",
        "--json",
    )

    # When: archiving that memory key and hydrating context for Codex.
    archive_result = _run_cli(
        "memory",
        "archive",
        "--key",
        "decision:legacy-placement-rule",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    hydrate_result = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-codex",
        "--json",
    )

    # Then: archived detail is recoverable by reference but absent from default hydration.
    assert upsert_result.returncode == 0, upsert_result.stderr
    assert archive_result.returncode == 0, archive_result.stdout
    assert hydrate_result.returncode == 0, hydrate_result.stderr
    archive_payload = json.loads(archive_result.stdout)
    hydrate_payload = json.loads(hydrate_result.stdout)
    assert archive_payload["status"] == "PASS"
    assert archive_payload["archived"]["key"] == "decision:legacy-placement-rule"
    assert archive_payload["archived"]["hydrated_by_default"] is False
    hydrated_keys = {entry["key"] for entry in hydrate_payload["memory"]}
    assert "decision:legacy-placement-rule" not in hydrated_keys


def test_session_summarize_returns_refs_without_private_paths(tmp_path: Path) -> None:
    # Given: private trace and audit records already written by earlier V3 operations.
    state_dir = tmp_path / ".chat-lms-state"
    trace_dir = state_dir / "trace"
    audit_dir = state_dir / "audit"
    trace_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    _write_jsonl(
        trace_dir / "trace-log.jsonl",
        {
            "schema_version": "trace-v1",
            "trace_id": "trace_session_001",
            "event_type": "command",
            "profile_root": "<profile-root>",
            "summary": "Ran memory compact for the private profile.",
        },
    )
    _write_jsonl(
        audit_dir / "audit-log.jsonl",
        {
            "schema_version": "audit-v1",
            "audit_id": "audit_session_001",
            "operation": "memory.compact",
            "profile_root": "<profile-root>",
            "summary": "Compacted memory summary.",
        },
    )

    # When: summarizing the session for closeout.
    result = _run_cli("session", "summarize", "--profile-root", str(tmp_path), "--json")

    # Then: the summary points to journal refs, not raw runtime paths.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == "session-summary-v1"
    assert payload["profile_root"] == "<profile-root>"
    assert payload["trace_refs"] == ["trace_session_001"]
    assert payload["audit_refs"] == ["audit_session_001"]
    assert str(tmp_path) not in result.stdout


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


def _write_jsonl(path: Path, payload: dict[str, str]) -> None:
    _ = path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
