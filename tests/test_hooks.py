from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.state import ProfileState, bump_session_counter


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
    expected_codes = {
        "SessionStart": 0,
        "UserPromptSubmit": 0,
        "PostToolUse": 0,
        "PostCompact": 0,
        "Stop": 0,
    }

    for event_name, event_hooks in hooks.items():
        payload = json.dumps({"session_id": "test-session", "hook_event_name": event_name})
        for hook in event_hooks:
            result = _run_hook_command(repo_root, hook["command"], payload)
            assert result.returncode == expected_codes[event_name], hook["command"]
            assert "Traceback" not in result.stderr
            if event_name == "PostCompact":
                assert result.stdout == ""


def test_stop_hook_active_is_noop() -> None:
    # Given: a profile blocked by unrecorded academy DB obligations.
    init = _run_hook_cli('{"session_id": "s1"}', "academy-db", "init", "--json")
    assert init.returncode == 0, init.stderr

    # When: the Stop hook re-fires with stop_hook_active set by the host.
    result = _run_hook_cli(
        '{"session_id": "s1", "stop_hook_active": true}',
        "hook",
        "stop",
        "--verify-memory",
        "--json",
    )

    # Then: the gate does not re-block (no infinite block ping-pong).
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["skipped"] == "stop_hook_active"


def test_third_identical_block_escalates() -> None:
    # Given: a profile blocked by a condition only the teacher can resolve.
    init = _run_hook_cli('{"session_id": "s-esc"}', "academy-db", "init", "--json")
    assert init.returncode == 0, init.stderr
    stdin = '{"session_id": "s-esc"}'

    # When: the same blocker signature repeats three times in one session.
    first = _run_hook_cli(stdin, "hook", "stop", "--verify-memory", "--json")
    second = _run_hook_cli(stdin, "hook", "stop", "--verify-memory", "--json")
    third = _run_hook_cli(stdin, "hook", "stop", "--verify-memory", "--json")

    # Then: the first two block, the third escalates to the teacher instead of looping.
    assert first.returncode == 5
    assert json.loads(first.stdout)["decision"] == "block"
    assert second.returncode == 5
    assert third.returncode == 0, third.stdout
    escalated = json.loads(third.stdout)
    assert escalated["escalated"] is True
    assert "교사" in json.dumps(escalated, ensure_ascii=False)


def test_post_compact_emits_nothing() -> None:
    # Given: a profile blocked by unrecorded obligations (worst case for the old seam).
    init = _run_hook_cli('{"session_id": "s1"}', "academy-db", "init", "--json")
    assert init.returncode == 0, init.stderr

    # When: the PostCompact hook fires.
    result = _run_hook_cli('{"session_id": "s1"}', "hook", "post-compact", "--json")

    # Then: nothing is emitted (the host rejects compact stdout) and a recovery
    # marker is stored for the next session-start.
    assert result.returncode == 0, result.stdout
    assert result.stdout == ""
    profile_root = Path(os.environ["CHAT_LMS_AGENT_PROFILE_ROOT"])
    marker = profile_root / ".chat-lms-state" / "compact-recovery.json"
    assert marker.exists()


def test_block_counter_scoped_by_session(tmp_path: Path) -> None:
    # Given: a private profile and two distinct Codex sessions.
    repo_root = Path(__file__).resolve().parents[1]
    profile = ProfileState(root=tmp_path / "profile", repo_root=repo_root)

    # When: the same blocker signature repeats within and across sessions.
    first = bump_session_counter(profile, "session-a", "blocker-sig")
    second = bump_session_counter(profile, "session-a", "blocker-sig")
    other_session = bump_session_counter(profile, "session-b", "blocker-sig")
    traversal = bump_session_counter(profile, "../../evil", "blocker-sig")

    # Then: counters are session-scoped and ids are path-sanitized.
    assert (first, second, other_session) == (1, 2, 1)
    assert traversal == 1
    sessions_dir = tmp_path / "profile" / ".chat-lms-state" / "sessions"
    assert (sessions_dir / "session-a" / "counters.json").exists()
    for child in sessions_dir.iterdir():
        assert sessions_dir in child.resolve().parents


def _run_hook_cli(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root,
        env=env,
        input=stdin,
        capture_output=True,
        check=False,
        text=True,
    )


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


def test_user_prompt_submit_injects_wordbook_prompt_route() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    payload = json.dumps(
        {
            "session_id": "prompt-route-session",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "과외 가상학생 학생 단어 현황 보고",
        },
        ensure_ascii=False,
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chat_lms_agent",
            "hook",
            "user-prompt-submit",
            "--json",
        ],
        cwd=repo_root,
        env=env,
        input=payload,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    hook_payload = json.loads(result.stdout)
    context = json.loads(hook_payload["hookSpecificOutput"]["additionalContext"])
    route = context["prompt_route"]
    assert route["status"] == "MATCHED"
    assert route["student_argument"] == "가상학생"
    assert route["first_command"].startswith("agent-tools prompt-check")
    assert '--student "가상학생"' in route["then_command"]
    assert route["then_command"].startswith("side-panel wordbook open-plan")
    assert "do not create a new HTML report for this request" in route["must_not"]


def test_context_hydrate_includes_prompt_routing_policy() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

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
    context = json.loads(result.stdout)
    policy = context["prompt_routing"]
    assert policy["mandatory_gate"].startswith("agent-tools prompt-check")
    assert "과외 <학생> 학생 단어 현황 보고" in policy["wordbook_requests"]["examples"]
    assert "do not create a new report generator" in policy["wordbook_requests"]["must_not"]


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
