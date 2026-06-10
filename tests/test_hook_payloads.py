from __future__ import annotations

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

from chat_lms_agent.hook_payloads import HookPayload, read_hook_payload


def test_post_tool_use_payload_extracts_changed_files() -> None:
    # Given: a Codex PostToolUse payload naming a managed registry path.
    payload = {
        "session_id": "test-session",
        "hook_event_name": "PostToolUse",
        "tool_response": {
            "changed_files": ["src/chat_lms_agent/agent_tools.py"],
        },
    }

    # When: the hook receives the payload on stdin.
    result = _run_cli_with_stdin(
        json.dumps(payload),
        "hook",
        "post-tool-use",
        "--json",
    )

    # Then: the registry memory guard uses the stdin changed file.
    assert result.returncode == 5, result.stdout
    hook_payload = json.loads(result.stdout)
    assert hook_payload["error_code"] == "MEMORY_UPDATE_REQUIRED"
    assert hook_payload["changed_files"] == ["src/chat_lms_agent/agent_tools.py"]


def test_malformed_hook_payload_returns_contract_error_without_traceback() -> None:
    # Given: malformed JSON arrives on stdin.
    malformed = "{bad json"

    # When: the hook is invoked through the real CLI.
    result = _run_cli_with_stdin(
        malformed,
        "hook",
        "post-tool-use",
        "--json",
    )

    # Then: the CLI returns a stable JSON error without a traceback.
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INVALID_HOOK_PAYLOAD"
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_oversized_stdin_rejected() -> None:
    # Given: a syntactically valid payload above the 1 MiB ingress cap.
    huge = '{"hook_event_name": "Stop", "padding": "' + "x" * 1_048_576 + '"}'

    # When: the hook is invoked through the real CLI.
    result = _run_cli_with_stdin(huge, "hook", "stop", "--json")

    # Then: the payload is rejected at the ingress, never parsed or acted on.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "INVALID_HOOK_PAYLOAD"
    assert "too large" in payload["message"]


def test_lifecycle_fields_parsed() -> None:
    # Given: a payload carrying the native lifecycle fields.
    raw = json.dumps(
        {
            "hook_event_name": "Stop",
            "session_id": "s-1",
            "stop_hook_active": True,
            "source": "compact",
            "trigger": "PostCompact",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
        },
    )

    # When: the payload is read.
    result = read_hook_payload(StringIO(raw), event_name="stop")

    # Then: every lifecycle field survives parsing.
    assert isinstance(result, HookPayload)
    assert result.stop_hook_active is True
    assert result.source == "compact"
    assert result.trigger == "PostCompact"
    assert result.tool_name == "Bash"
    assert result.tool_input == {"command": "echo hi"}


def test_lifecycle_fields_default_safely() -> None:
    # Given: a payload without any lifecycle fields.
    result = read_hook_payload(StringIO('{"hook_event_name": "Stop"}'), event_name="stop")

    # Then: defaults are safe (no accidental no-op or gate trigger).
    assert isinstance(result, HookPayload)
    assert result.stop_hook_active is False
    assert result.source is None
    assert result.trigger is None
    assert result.tool_name is None
    assert result.tool_input is None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli_with_stdin(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
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
