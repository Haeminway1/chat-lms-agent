from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_hydrate_includes_hook_memory_tool_and_academy_inventory(tmp_path: Path) -> None:
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    hydrate_result = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-codex",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert hydrate_result.returncode == 0, hydrate_result.stderr
    payload = json.loads(hydrate_result.stdout)
    assert {"hook_lifecycle", "memory_obligations", "tool_lifecycle", "academy_db"} <= set(
        payload,
    )
    assert payload["academy_db"]["schema_version"] == "academy-v1"
    assert payload["hook_lifecycle"]["registered_events"] == [
        "PostCompact",
        "PostToolUse",
        "PreToolUse",
        "SessionStart",
        "Stop",
        "UserPromptSubmit",
    ]
    assert payload["hook_lifecycle"]["event_liveness"] == [
        {"event": "PostCompact", "fires_at_runtime": False},
        {"event": "PostToolUse", "fires_at_runtime": False},
        {"event": "PreToolUse", "fires_at_runtime": False},
        {"event": "SessionStart", "fires_at_runtime": True},
        {"event": "Stop", "fires_at_runtime": False},
        {"event": "UserPromptSubmit", "fires_at_runtime": False},
    ]
    assert "SessionStart" in payload["hook_lifecycle"]["liveness_note"]


def test_hydrate_does_not_leak_private_runtime_paths(tmp_path: Path) -> None:
    result = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-codex",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert str(tmp_path) not in result.stdout


def test_session_start_compact_recovery_injected_once() -> None:
    # Given: a compaction happened (PostCompact stored a pending recovery marker).
    init = _run_hook_cli('{"session_id": "s1"}', "academy-db", "init", "--json")
    assert init.returncode == 0, init.stderr
    compacted = _run_hook_cli('{"session_id": "s1"}', "hook", "post-compact", "--json")
    assert compacted.returncode == 0, compacted.stdout

    # When: the next session-start fires, then another one after it.
    first = _run_hook_cli('{"session_id": "s1"}', "hook", "session-start", "--json")
    second = _run_hook_cli('{"session_id": "s1"}', "hook", "session-start", "--json")

    # Then: recovery context is injected exactly once (claim semantics).
    assert first.returncode == 0, first.stdout
    first_context = _additional_context(first.stdout)
    assert "compact_recovery" in first_context
    assert second.returncode == 0, second.stdout
    assert "compact_recovery" not in _additional_context(second.stdout)


def test_user_prompt_submit_is_fallback_claim() -> None:
    # Given: a pending recovery marker that no session-start has claimed.
    init = _run_hook_cli('{"session_id": "s2"}', "academy-db", "init", "--json")
    assert init.returncode == 0, init.stderr
    compacted = _run_hook_cli('{"session_id": "s2"}', "hook", "post-compact", "--json")
    assert compacted.returncode == 0, compacted.stdout

    # When: the next user prompt arrives before any session-start.
    result = _run_hook_cli(
        '{"session_id": "s2", "prompt": "다음 수업 준비"}',
        "hook",
        "user-prompt-submit",
        "--json",
    )

    # Then: the prompt-submit hook claims and injects the recovery context.
    assert result.returncode == 0, result.stdout
    assert "compact_recovery" in _additional_context(result.stdout)


def _additional_context(stdout: str) -> dict[str, object]:
    envelope = json.loads(stdout)
    hook_output = envelope["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    context = json.loads(hook_output["additionalContext"])
    assert isinstance(context, dict)
    return context


def _run_hook_cli(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        input=stdin,
        capture_output=True,
        check=False,
        text=True,
    )


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
