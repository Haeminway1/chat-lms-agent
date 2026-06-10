from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.pre_tool_gate import evaluate_tool_call
from chat_lms_agent.state import ProfileState
from tests.trace_audit_approval_support import (
    approve_interactively,
    artifact_files,
    create_planned_approval,
)


def _profile(tmp_path: Path) -> ProfileState:
    return ProfileState(root=tmp_path / "profile", repo_root=_repo_root())


def test_decision_table_truth_table(tmp_path: Path) -> None:
    # Given: the pure decision table over tier x policy x override.
    profile = _profile(tmp_path)

    # Then: known read tools pass without ceremony.
    read_decision = evaluate_tool_call(profile, "read", {"file_path": "notes.md"})
    assert (read_decision.permission, read_decision.tier) == ("allow", "read")

    # Then: unknown tool classes resolve to a teacher prompt, never silent allow.
    unknown = evaluate_tool_call(profile, "mystery_tool", {})
    assert unknown.permission == "ask"

    # Then: a missing tool name is treated as unknown, not allowed.
    nameless = evaluate_tool_call(profile, None, None)
    assert nameless.permission == "ask"

    # Then: destructive commands against private data deny without an approval.
    destructive = {"command": "Remove-Item -Recurse <profile-root>/.chat-lms-state/academy"}
    denied = evaluate_tool_call(profile, "Bash", destructive)
    assert denied.permission == "deny"
    assert denied.tier == "exec"

    # Then: harmless bash stays allowed.
    harmless = evaluate_tool_call(profile, "Bash", {"command": "git status"})
    assert harmless.permission == "allow"


def test_destructive_db_command_denied(tmp_path: Path) -> None:
    # Given: a destructive command aimed at the private academy data.
    stdin = json.dumps(
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "Remove-Item -Recurse data/academy"},
        },
    )

    # When: PreToolUse fires without any approved ledger entry.
    result = _run_hook_cli(stdin, "hook", "pre-tool-use", "--profile-root", str(tmp_path), "--json")

    # Then: the call is denied before execution.
    assert result.returncode == 5, result.stdout
    payload = json.loads(result.stdout)
    assert payload["permissionDecision"] == "deny"
    assert payload["error_code"] == "DESTRUCTIVE_WITHOUT_APPROVAL"

    # When: the teacher approves the pending operation interactively.
    approval_id, _ = create_planned_approval(tmp_path)
    code, approved = approve_interactively(tmp_path, approval_id, "human:owner")
    assert code == 0, approved

    # Then: the same destructive command is allowed to proceed.
    allowed = _run_hook_cli(
        stdin,
        "hook",
        "pre-tool-use",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert allowed.returncode == 0, allowed.stdout
    assert json.loads(allowed.stdout)["permissionDecision"] == "allow"


def test_state_dir_mutation_denied(tmp_path: Path) -> None:
    # Given: an edit aimed at the runtime-owned ledger directory.
    stdin = json.dumps(
        {
            "session_id": "s1",
            "tool_name": "write",
            "tool_input": {
                "file_path": ".chat-lms-state/approvals.json",
                "content": '{"records": []}',
            },
        },
    )

    # When: PreToolUse fires.
    result = _run_hook_cli(stdin, "hook", "pre-tool-use", "--profile-root", str(tmp_path), "--json")

    # Then: ledgers are runtime-owned; the sanctioned CLI is named.
    assert result.returncode == 5, result.stdout
    payload = json.loads(result.stdout)
    assert payload["permissionDecision"] == "deny"
    assert payload["error_code"] == "RUNTIME_OWNED_STATE"
    assert "chat_lms_agent" in payload["reason"]


def test_public_repo_write_with_private_reference_denied(tmp_path: Path) -> None:
    # Given: a write landing inside the public repo whose content references
    # the private profile state.
    stdin = json.dumps(
        {
            "session_id": "s1",
            "tool_name": "write",
            "tool_input": {
                "file_path": str(_repo_root() / "docs" / "leak.md"),
                "content": "private ledger lives at .chat-lms-state/approvals.json",
            },
        },
    )

    # When: PreToolUse fires.
    result = _run_hook_cli(stdin, "hook", "pre-tool-use", "--profile-root", str(tmp_path), "--json")

    # Then: the boundary direction (private -> public) is enforced.
    assert result.returncode == 5, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "PRIVATE_REFERENCE_IN_PUBLIC_WRITE"


def test_denials_are_journaled(tmp_path: Path) -> None:
    # Given: a deny-producing call.
    stdin = json.dumps(
        {
            "session_id": "s1",
            "tool_name": "write",
            "tool_input": {"file_path": ".chat-lms-state/memory.json", "content": "{}"},
        },
    )
    result = _run_hook_cli(stdin, "hook", "pre-tool-use", "--profile-root", str(tmp_path), "--json")
    assert result.returncode == 5, result.stdout

    # Then: the denial leaves a trace record naming the rule.
    trace_files = artifact_files(tmp_path / ".chat-lms-state", "trace")
    assert trace_files, "expected a trace record for the denial"
    combined = " ".join(path.read_text(encoding="utf-8") for path in trace_files)
    assert "RUNTIME_OWNED_STATE" in combined


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_hook_cli(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
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
