from __future__ import annotations

import json
import os
import subprocess
from hashlib import sha256
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
    # The wrapper must forward args via the automatic $args (no named-parameter
    # block), so flags like --out are not stolen by PowerShell's -OutVariable/-OutBuffer.
    assert "[Parameter(ValueFromRemainingArguments" not in cli_script
    assert "$CliArgs" not in cli_script
    assert "@args" in cli_script
    assert "Test-PythonRuntime" not in cli_script
    assert "sys.version_info" not in cli_script
    assert "[Console]::InputEncoding" in cli_script
    assert "[Console]::OutputEncoding" in cli_script
    session_start_script = session_start_script_path.read_text(encoding="utf-8")
    assert "Get-Content -Raw -Encoding UTF8" in session_start_script
    assert "panel, viewer, wordbook, or write-action style request" in session_start_script
    assert "command_index is already injected by the SessionStart hook" in session_start_script
    assert (
        "Run the matching route_packs.command_index first_command directly"
        in session_start_script
    )
    assert "agent-tools prompt-check" in session_start_script
    assert "recommended fallback" in session_start_script
    assert "pass --profile-root so profile routes are visible" in session_start_script
    assert (
        "matched route is already injected by the UserPromptSubmit hook"
        not in session_start_script
    )
    assert "Do not manually re-run agent-tools prompt-check" not in session_start_script
    assert "run agent-tools prompt-check first" not in session_start_script
    assert "Never create new HTML files for these routed requests" in session_start_script
    assert "ad-hoc analyses not covered by any route" in session_start_script
    assert "For learner wordbook requests" not in session_start_script
    assert "wordbook status report" not in session_start_script


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
        encoding="utf-8",
        errors="replace",
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert hook_result.returncode == 0, hook_result.stderr
    assert str(workspace) not in hook_result.stdout


def test_user_mode_generates_isolated_teacher_codex_home(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)

    profile_root = _profile_root(tmp_path, "qa-demo")
    workspace = profile_root / "codex-workspace"
    codex_home = profile_root / "codex-home"
    config_path = codex_home / "config.toml"
    launcher_path = codex_home / "launch-teacher-codex.cmd"

    assert result.returncode == 0, result.stderr
    assert config_path.exists()
    assert launcher_path.exists()
    config = config_path.read_text(encoding="utf-8")
    launcher = launcher_path.read_text(encoding="utf-8")
    assert config.startswith('model = "gpt-5.5"')
    assert '[plugins."chat-lms-agent@chatlms"]' in config
    assert config.count("[plugins.") == 1
    assert "enabled = true" in config
    assert "[marketplaces.chatlms]" in config
    assert f"source = '{_repo_root()}\\codex-plugin'" in config
    assert f"[projects.'{workspace}']" in config
    assert 'trust_level = "trusted"' in config
    assert 'set "CODEX_HOME=' in launcher
    assert str(codex_home) in launcher
    assert "OpenAI.Codex" in launcher
    for forbidden in (
        "child_agents_md",
        "omo",
        "[agents.",
        "multi_agent",
        "enable_fanout",
        "shell_environment_policy",
    ):
        assert forbidden not in config


def test_user_mode_teacher_codex_home_is_idempotent(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    first_result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)
    config_path = _profile_root(tmp_path, "qa-demo") / "codex-home" / "config.toml"
    first_config = config_path.read_text(encoding="utf-8")
    second_result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)
    second_config = config_path.read_text(encoding="utf-8")

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert second_config == first_config


def test_session_start_hydrate_skips_runtime_sync_when_bootstrap_hash_is_unchanged(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)

    workspace = _profile_root(tmp_path, "qa-demo") / "codex-workspace"
    session_start_script_path = workspace / "scripts" / "session-start-hydrate.ps1"
    sync_state_path = workspace / ".chat-lms-sync-state.json"
    watched_files = (
        workspace / "AGENTS.md",
        workspace / "hooks" / "hooks.json",
        workspace / "scripts" / "chat-lms-cli.ps1",
        session_start_script_path,
    )
    first_hydrate = _run_powershell_script(session_start_script_path, env=env, cwd=workspace)
    hashes_after_first_hydrate = {
        path.name: _file_sha256(path)
        for path in watched_files
    }
    second_hydrate = _run_powershell_script(session_start_script_path, env=env, cwd=workspace)
    hashes_after_second_hydrate = {
        path.name: _file_sha256(path)
        for path in watched_files
    }
    if not sync_state_path.exists():
        sync_log = _profile_root(tmp_path, "qa-demo") / "logs" / "session-start-sync.log"
        log_text = (
            sync_log.read_text(encoding="utf-8", errors="replace")
            if sync_log.exists()
            else "<no sync log written — hydrate aborted before logging>"
        )
        msg = (
            "sync-state file was never written.\n"
            f"hydrate1 rc={first_hydrate.returncode} stderr={first_hydrate.stderr!r}\n"
            f"hydrate1 stdout(tail)={(first_hydrate.stdout or '')[-600:]!r}\n"
            f"hydrate2 rc={second_hydrate.returncode} stderr={second_hydrate.stderr!r}\n"
            f"sync log:\n{log_text}"
        )
        raise AssertionError(msg)
    sync_state = json.loads(sync_state_path.read_text(encoding="utf-8-sig"))
    expected_bootstrap_hash = _file_sha256(_repo_root() / "scripts" / "bootstrap.ps1")

    assert result.returncode == 0, result.stderr
    assert first_hydrate.returncode == 0, first_hydrate.stderr
    assert second_hydrate.returncode == 0, second_hydrate.stderr
    assert sync_state["status"] == "skipped-unchanged"
    assert sync_state["bootstrapHash"] == expected_bootstrap_hash
    assert hashes_after_second_hydrate == hashes_after_first_hydrate


def test_user_mode_teacher_codex_home_stays_under_temp_profile_root(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    env["APPDATA"] = str(tmp_path / "roaming")

    result = _run_bootstrap("-Mode", "User", "-Profile", "qa-demo", env=env)

    profile_root = _profile_root(tmp_path, "qa-demo")
    config_path = profile_root / "codex-home" / "config.toml"
    launcher_path = profile_root / "codex-home" / "launch-teacher-codex.cmd"
    bootstrap_source = (_repo_root() / "scripts" / "bootstrap.ps1").read_text(
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr
    assert config_path.is_relative_to(profile_root)
    assert launcher_path.is_relative_to(profile_root)
    assert "\\.codex\\config.toml" not in bootstrap_source


def _profile_root(tmp_path: Path, profile: str) -> Path:
    return tmp_path / "local" / "ChatLMSAgent" / "profiles" / profile


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest().upper()


def _run_powershell_script(
    path: Path,
    *,
    env: dict[str, str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
    )


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
        encoding="utf-8",
        errors="replace",
        text=True,
    )
