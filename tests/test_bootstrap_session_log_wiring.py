from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _profile_root(tmp_path: Path, profile: str) -> Path:
    return tmp_path / "local" / "ChatLMSAgent" / "profiles" / profile


def _run_bootstrap(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
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
        encoding="utf-8",
        text=True,
    )


def test_user_mode_wires_notify_and_sessionstart_ingest(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)

    profile_root = _profile_root(tmp_path, "qa-demo")
    workspace = profile_root / "codex-workspace"
    config = (profile_root / "codex-home" / "config.toml").read_text(encoding="utf-8")
    notify_script_path = workspace / "scripts" / "chat-lms-notify.ps1"
    hydrate = (workspace / "scripts" / "session-start-hydrate.ps1").read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    # Native Codex notify is wired in the isolated teacher config (still a
    # top-level key, so the config still starts with the model line).
    assert config.startswith('model = "gpt-5.5"')
    assert "notify = [" in config
    assert "chat-lms-notify.ps1" in config
    assert config.count("[plugins.") == 1
    # The notify program asks the harness to ingest rollouts for this home.
    assert notify_script_path.exists()
    notify_script = notify_script_path.read_text(encoding="utf-8")
    assert "session-log" in notify_script
    assert "ingest" in notify_script
    assert str(profile_root) in notify_script
    # SessionStart launches a detached catch-up ingest as a safety net.
    assert "session-log" in hydrate
    assert "ingest" in hydrate
    assert "Start-Process" in hydrate
    # Regression: ingest must NOT pin --transcript-home. The isolated teacher
    # codex-home never receives rollouts on MSIX Desktop (the launcher does not
    # take effect there), and an explicit home disables fallback discovery, so
    # pinning it silently ingests nothing. Omitting the flag lets discovery fall
    # through CODEX_HOME env -> isolated home -> the default ~/.codex sessions.
    assert "--transcript-home" not in notify_script
    assert "--transcript-home" not in hydrate


def test_user_mode_notify_wiring_is_idempotent(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    first = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)
    notify_path = (
        _profile_root(tmp_path, "qa-demo") / "codex-workspace" / "scripts" / "chat-lms-notify.ps1"
    )
    first_notify = notify_path.read_text(encoding="utf-8")
    second = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)
    second_notify = notify_path.read_text(encoding="utf-8")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first_notify == second_notify
