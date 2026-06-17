from __future__ import annotations

import subprocess
from pathlib import Path


def test_bootstrap_dry_run_lists_zero_touch_actions() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/bootstrap.ps1",
            "-DryRun",
        ],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "BOOTSTRAP_DRY_RUN PASS" in result.stdout
    # Dev mode is zero-touch: it lists honest next steps (the dev path is uv-based
    # and real provisioning is -Mode User), not no-op actions it never performs.
    assert "uv sync" in result.stdout
    assert "uv run pytest" in result.stdout
    assert "-Mode User" in result.stdout
    assert "codex-plugin" in result.stdout


def test_bootstrap_user_mode_dry_run_lists_private_runtime_actions() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/bootstrap.ps1",
            "-DryRun",
            "-Mode",
            "User",
            "-Profile",
            "teacher-demo",
        ],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "BOOTSTRAP_DRY_RUN PASS" in result.stdout
    assert "MODE User" in result.stdout
    assert "PROFILE teacher-demo" in result.stdout
    assert "private profile folders" in result.stdout
    assert "private AGENTS.md" in result.stdout
    assert "SessionStart hydrate hook" in result.stdout
    assert "safe runtime auto-sync" in result.stdout
