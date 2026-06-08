from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


def test_invalid_doctor_flag_is_rejected() -> None:
    result = _run_cli("doctor", "--totally-invalid", "--json")

    assert result.returncode == 2


def test_session_closeout_verify_memory_is_available() -> None:
    result = _run_cli("session", "closeout", "--verify-memory", "--json")

    assert result.returncode in {0, 5}


def test_tool_list_supports_profile_root_json() -> None:
    repo_root = _repo_root()
    result = _run_cli("tool", "list", "--json", "--profile-root", str(repo_root / ".tmp-tool-list"))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"


def test_tool_list_supports_fixture_profile_name() -> None:
    result = _run_cli("tool", "list", "--json", "--profile", "test-fixture")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["tools"][0]["name"] == "fixture_lookup"


def test_public_repo_root_is_rejected_as_profile_root() -> None:
    result = _run_cli("profile", "inspect", "--profile-root", str(_repo_root()), "--json")

    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "PUBLIC_REPO_STATE_REJECTED"


def test_hydrate_includes_active_tools_and_memory() -> None:
    with _temp_profile_root("hydrate") as profile_root:
        draft_result = _run_cli(
            "tool",
            "draft",
            "--profile-root",
            str(profile_root),
            "--name",
            "attendance_lookup",
            "--kind",
            "query_template",
            "--summary",
            "Find the latest attendance summary.",
            "--command",
            "python -m chat_lms_agent doctor --json",
            "--json",
        )
        assert draft_result.returncode == 0, draft_result.stderr

        activate_result = _run_cli(
            "tool",
            "activate",
            "--profile-root",
            str(profile_root),
            "--name",
            "attendance_lookup",
            "--json",
        )
        assert activate_result.returncode == 0, activate_result.stderr

        memory_result = _run_cli(
            "memory",
            "upsert",
            "--profile-root",
            str(profile_root),
            "--key",
            "tool:attendance_lookup",
            "--scope",
            "workspace",
            "--text",
            "Use this tool for attendance summaries and keep SERVICE_SECRET=redacted.",
            "--json",
        )
        assert memory_result.returncode == 0, memory_result.stderr

        hydrate_result = _run_cli(
            "context",
            "hydrate",
            "--for-codex",
            "--profile-root",
            str(profile_root),
            "--json",
        )

        assert hydrate_result.returncode == 0, hydrate_result.stderr
        payload = json.loads(hydrate_result.stdout)
        assert payload["active_tools"][0]["name"] == "attendance_lookup"
        assert payload["memory"][0]["key"] == "tool:attendance_lookup"
        assert "SERVICE_SECRET" not in hydrate_result.stdout


def test_closeout_blocks_when_active_tool_has_no_memory() -> None:
    with _temp_profile_root("closeout") as profile_root:
        draft_result = _run_cli(
            "tool",
            "draft",
            "--profile-root",
            str(profile_root),
            "--name",
            "grade_digest",
            "--kind",
            "workflow",
            "--summary",
            "Summarize grading status.",
            "--template",
            "Run grading digest workflow.",
            "--json",
        )
        assert draft_result.returncode == 0, draft_result.stderr

        activate_result = _run_cli(
            "tool",
            "activate",
            "--profile-root",
            str(profile_root),
            "--name",
            "grade_digest",
            "--json",
        )
        assert activate_result.returncode == 0, activate_result.stderr

        closeout_result = _run_cli(
            "session",
            "closeout",
            "--verify-memory",
            "--profile-root",
            str(profile_root),
            "--json",
        )

        assert closeout_result.returncode == 5
        payload = json.loads(closeout_result.stdout)
        assert payload["missing_memory"] == ["tool:grade_digest"]


def test_hook_commands_from_hooks_json_execute() -> None:
    hooks_path = _repo_root() / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))

    commands = [
        hook["command"]
        for event_hooks in hooks.values()
        for hook in event_hooks
    ]

    for command in commands:
        result = _run_hook_command(command)
        assert result.returncode in {0, 5}, command


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return env


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=_base_env(),
        capture_output=True,
        check=False,
        text=True,
    )


def _run_hook_command(command: str) -> subprocess.CompletedProcess[str]:
    parts = command.split()
    executable = [sys.executable, *parts[1:]]
    return subprocess.run(
        executable,
        cwd=_repo_root(),
        env=_base_env(),
        capture_output=True,
        check=False,
        text=True,
    )


@contextmanager
def _temp_profile_root(prefix: str) -> Iterator[Path]:
    with TemporaryDirectory(prefix=f"chat-lms-{prefix}-") as temp_dir:
        yield Path(temp_dir)
