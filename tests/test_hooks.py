from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_hooks_config_registers_session_start_and_stop() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    hooks_path = repo_root / "hooks" / "hooks.json"

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))

    assert "SessionStart" in hooks
    assert "Stop" in hooks


def test_hooks_json_registers_full_lifecycle() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    hooks_path = repo_root / "hooks" / "hooks.json"

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))

    assert set(hooks) == {
        "SessionStart",
        "UserPromptSubmit",
        "PostToolUse",
        "PostCompact",
        "Stop",
    }


def test_every_lifecycle_hook_executes_with_fixture_payload() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    hooks_path = repo_root / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))

    for event_name, event_hooks in hooks.items():
        payload = json.dumps({"session_id": "test-session", "hook_event_name": event_name})
        for hook in event_hooks:
            result = _run_hook_command(repo_root, hook["command"], payload)
            assert result.returncode in {0, 5}, hook["command"]
            assert "Traceback" not in result.stderr


def test_context_hydrate_outputs_redacted_codex_context() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["CLASSCARD_PASSWORD"] = "should-not-leak"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chat_lms_agent",
            "context",
            "hydrate",
            "--for-codex",
            "--json",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["runtime"] == "Codex Desktop"
    assert "should-not-leak" not in result.stdout


def test_stop_hook_blocks_tool_registry_change_without_memory_update() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chat_lms_agent",
            "hook",
            "stop",
            "--verify-memory",
            "--changed-files",
            "src/chat_lms_agent/agent_tools.py",
            "--json",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "MEMORY_UPDATE_REQUIRED"


def _run_hook_command(
    repo_root: Path,
    command: str,
    stdin: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    parts = command.split()
    return subprocess.run(
        [sys.executable, *parts[1:]],
        cwd=repo_root,
        env=env,
        input=stdin,
        capture_output=True,
        check=False,
        text=True,
    )
