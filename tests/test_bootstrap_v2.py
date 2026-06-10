from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_bootstrap_dry_run_lists_python_cli_delegation() -> None:
    result = _run_bootstrap("-DryRun", "-Mode", "User", "-Profile", "qa-demo")

    assert result.returncode == 0, result.stderr
    assert "python -m chat_lms_agent bootstrap plan" in result.stdout
    assert "python -m chat_lms_agent bootstrap apply" in result.stdout
    assert "python -m chat_lms_agent bootstrap sync-runtime" in result.stdout


def test_user_mode_generates_full_lifecycle_hooks_in_temp_env(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)

    profile_root = (
        tmp_path
        / "local"
        / "ChatLMSAgent"
        / "profiles"
        / "qa-demo"
    )
    workspace = profile_root / "codex-workspace"
    hooks_path = workspace / "hooks" / "hooks.json"
    cli_script_path = workspace / "scripts" / "chat-lms-cli.ps1"
    session_start_script_path = workspace / "scripts" / "session-start-hydrate.ps1"
    hooks_text = hooks_path.read_text(encoding="utf-8-sig")
    hooks = json.loads(hooks_text)["hooks"]
    commands = [
        item["hooks"][0]["command"]
        for event_name, event_items in hooks.items()
        for item in event_items
        if event_name != "SessionStart"
    ]
    assert result.returncode == 0, result.stderr
    for event_name in ("SessionStart", "UserPromptSubmit", "PostToolUse", "PostCompact", "Stop"):
        assert event_name in hooks_text
    assert cli_script_path.exists()
    assert all(str(profile_root) in command for command in commands)
    assert all("chat-lms-cli.ps1" in command for command in commands)
    assert all("--profile-root" in command for command in commands)
    cli_script = cli_script_path.read_text(encoding="utf-8")
    assert 'Join-Path $repoRoot "src"' in cli_script
    assert "Get-Command py" in cli_script
    assert "-3 -m chat_lms_agent" in cli_script
    assert "Python 3.12+" in cli_script
    assert "[Console]::InputEncoding" in cli_script
    assert "[Console]::OutputEncoding" in cli_script
    session_start_script = session_start_script_path.read_text(encoding="utf-8")
    assert "Get-Content -Raw -Encoding UTF8" in session_start_script
    assert "agent-tools prompt-check first" in session_start_script
    assert "wordbook status report" in session_start_script
    assert "Do not inspect DB schema" in session_start_script
    assert "or search files with rg" in session_start_script


def test_user_mode_generated_hook_runs_against_private_profile(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)

    workspace = (
        tmp_path
        / "local"
        / "ChatLMSAgent"
        / "profiles"
        / "qa-demo"
        / "codex-workspace"
    )
    hooks_path = workspace / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8-sig"))["hooks"]
    command = hooks["UserPromptSubmit"][0]["hooks"][0]["command"]
    payload = json.dumps({"session_id": "qa-session", "hook_event_name": "UserPromptSubmit"})

    hook_result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=workspace,
        env=env,
        input=payload,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert hook_result.returncode == 0, hook_result.stderr
    assert str(workspace) not in hook_result.stdout


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_bootstrap(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/bootstrap.ps1",
            *args,
        ],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
