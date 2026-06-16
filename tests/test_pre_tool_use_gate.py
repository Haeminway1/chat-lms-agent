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


def test_raw_db_mutation_denied_without_approval(tmp_path: Path) -> None:
    # Given: raw sqlite mutation commands aimed at a database file.
    profile = _profile(tmp_path)
    chat_lms_db = "data/chat_lms.db"
    academy_sqlite = "academy.sqlite3"
    update_script = _sqlite_exec_script(
        chat_lms_db,
        "UPDATE student_session_records SET status = 1",
    )
    insert_script = _sqlite_exec_script(
        chat_lms_db,
        "INSERT INTO sessions DEFAULT VALUES",
    )
    delete_script = _sqlite_exec_script(academy_sqlite, "DELETE FROM sessions")
    commands = (
        f'py -c "{update_script}"',
        f'python -c "{insert_script}"',
        f'python -c "{delete_script}"',
        'sqlite3 chat_lms.db "DELETE FROM sessions"',
    )

    for command in commands:
        # When: PreToolUse evaluates the exec command without approval.
        decision = evaluate_tool_call(profile, "Bash", {"command": command})

        # Then: raw DB mutations are funneled away from direct SQL.
        assert decision.permission == "deny"
        assert decision.rule_id == "RAW_DB_WRITE_WITHOUT_APPROVAL"


def test_raw_db_mutation_allowed_with_approval(tmp_path: Path) -> None:
    # Given: a teacher-approved exceptional operation is present.
    profile = ProfileState(root=tmp_path, repo_root=_repo_root())
    approval_id, _ = create_planned_approval(tmp_path)
    code, approved = approve_interactively(tmp_path, approval_id, "human:owner")
    assert code == 0, approved

    # When: an exec command attempts a raw sqlite database mutation.
    decision = evaluate_tool_call(
        profile,
        "Bash",
        {"command": 'sqlite3 data/chat_lms.db "UPDATE sessions SET title = title"'},
    )

    # Then: the existing approval gate allows the exceptional raw write.
    assert decision.permission == "allow"
    assert decision.rule_id == "RAW_DB_WRITE_WITH_APPROVAL"


def test_write_action_and_read_harness_commands_do_not_trip_raw_db_gate(
    tmp_path: Path,
) -> None:
    # Given: sanctioned write-action and read/harness commands.
    profile = _profile(tmp_path)
    apply_args = "--from payload.json --profile-root <root> --json"
    commands = (
        f"python -m chat_lms_agent write-action apply --id record-class {apply_args}",
        "python -m chat_lms_agent write-action roster --profile-root <root> --json",
        "python -m chat_lms_agent academy-db query run learner-count --json",
        "python -m chat_lms_agent academy-db report build --json",
        "uv run pytest -q",
        "git status",
    )

    for command in commands:
        # When: PreToolUse evaluates the command.
        decision = evaluate_tool_call(profile, "Bash", {"command": command})

        # Then: ordinary safe commands continue through unchanged.
        assert decision.permission == "allow"
        assert decision.rule_id is None


def test_destructive_db_file_command_denied_without_approval(tmp_path: Path) -> None:
    # Given: a destructive command aimed at the private chat LMS database file.
    profile = _profile(tmp_path)

    # When: PreToolUse evaluates the command without approval.
    decision = evaluate_tool_call(
        profile,
        "Bash",
        {"command": "rm -rf /private/profile/data/chat_lms.db"},
    )

    # Then: database files are private data for destructive-command gating.
    assert decision.permission == "deny"
    assert decision.rule_id == "DESTRUCTIVE_WITHOUT_APPROVAL"


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


def _sqlite_exec_script(db_path: str, sql: str) -> str:
    return f"import sqlite3; sqlite3.connect('{db_path}').execute('{sql}')"


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
