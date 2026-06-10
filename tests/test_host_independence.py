from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.hosts import active_host


def _run_cli(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
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

# Catches host-coupling token forms ("Codex", "codex-workspace", ".codex-plugin",
# "codex_desktop", "build_codex_context", "--for-codex") while ignoring OSS
# project names like "lazycodex" that merely contain the substring.
_HOST_TOKEN_RE = re.compile(r"(?i)\bcodex\b|codex[-_]|[-_.]codex")

# The only modules allowed to know the host by name:
# - hosts.py: the adapter data itself
# - oss_references.py: pinned external-reference registry data
# - command_parser.py: the host-dialect CLI compat flag (--for-codex)
_ALLOWED_HOST_FILES = {"hosts.py", "oss_references.py", "command_parser.py"}


def test_core_modules_are_host_token_free() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "chat_lms_agent"
    offenders: dict[str, list[str]] = {}
    for path in sorted(src.glob("*.py")):
        if path.name in _ALLOWED_HOST_FILES:
            continue
        hits = [
            f"{line_number}: {line.strip()}"
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            )
            if _HOST_TOKEN_RE.search(line)
        ]
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"host tokens leaked into core modules: {offenders}"


def test_envelope_and_host_dialect_payloads_normalize_identically() -> None:
    # Given: the same event in host dialect and in the neutral envelope.
    from io import StringIO

    from chat_lms_agent.hook_payloads import read_hook_payload

    host_dialect = json.dumps(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s-1",
            "prompt": "다음 수업 준비",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        },
    )
    envelope = json.dumps(
        {
            "schema_version": "harness-event-v1",
            "event_type": "UserPromptSubmit",
            "session_id": "s-1",
            "prompt": "다음 수업 준비",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        },
    )

    # Then: both parse to the identical payload.
    first = read_hook_payload(StringIO(host_dialect), event_name="user-prompt-submit")
    second = read_hook_payload(StringIO(envelope), event_name="user-prompt-submit")
    assert first == second


def test_fake_host_drives_full_cycle_through_envelope(tmp_path: Path) -> None:
    # Given: a fake host that only speaks harness-event-v1 (no host field names).
    def envelope(event_type: str, **fields: object) -> str:
        return json.dumps(
            {
                "schema_version": "harness-event-v1",
                "host": "fake_host",
                "event_type": event_type,
                "session_id": "fake-1",
                **fields,
            },
            ensure_ascii=False,
        )

    profile_root = str(tmp_path / "fake-profile")
    init = _run_cli("", "academy-db", "init", "--profile-root", profile_root, "--json")
    assert init.returncode == 0, init.stderr

    # When: the fake host runs session-start, then tries to stop.
    started = _run_cli(
        envelope("SessionStart"),
        "hook",
        "session-start",
        "--profile-root",
        profile_root,
        "--json",
    )
    blocked = _run_cli(
        envelope("Stop"),
        "hook",
        "stop",
        "--verify-memory",
        "--profile-root",
        profile_root,
        "--json",
    )

    # Then: hydration and the native blocking contract answer the fake host.
    assert started.returncode == 0, started.stdout
    assert "hookSpecificOutput" in json.loads(started.stdout)
    assert blocked.returncode == 5, blocked.stdout
    blocked_payload = json.loads(blocked.stdout)
    assert blocked_payload["decision"] == "block"

    # When: the obligations are recorded and the fake host stops again.
    for key in ("decision:academy-db-schema", "schema:academy-db"):
        upsert = _run_cli(
            "",
            "memory",
            "upsert",
            "--key",
            key,
            "--scope",
            "durable",
            "--text",
            "기록 완료",
            "--profile-root",
            profile_root,
            "--json",
        )
        assert upsert.returncode == 0, upsert.stdout
    closed = _run_cli(
        envelope("Stop"),
        "hook",
        "stop",
        "--verify-memory",
        "--profile-root",
        profile_root,
        "--json",
    )

    # Then: the session closes cleanly — the host was never named.
    assert closed.returncode == 0, closed.stdout
    assert json.loads(closed.stdout)["status"] == "PASS"


def test_host_adapter_declares_identity_and_future_hosts() -> None:
    host = active_host()
    assert host.host_id == "codex_desktop"
    assert host.agent_actor == "codex_desktop_agent"
    assert host.runtime_label == "Codex Desktop"
    assert host.workspace_dirname == "codex-workspace"
    assert "standalone_desktop" in host.future_hosts
    assert "web_saas" in host.future_hosts
    assert host.host_files
