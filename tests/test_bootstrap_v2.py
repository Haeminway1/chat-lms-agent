from __future__ import annotations

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

    hooks_path = (
        tmp_path
        / "local"
        / "ChatLMSAgent"
        / "profiles"
        / "qa-demo"
        / "codex-workspace"
        / "hooks"
        / "hooks.json"
    )
    hooks_text = hooks_path.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    for event_name in ("SessionStart", "UserPromptSubmit", "PostToolUse", "PostCompact", "Stop"):
        assert event_name in hooks_text


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
