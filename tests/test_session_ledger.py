from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from chat_lms_agent import session_ledger
from chat_lms_agent.session_ledger import (
    export_session,
    ingest_rollouts,
    is_enabled,
    list_sessions,
    set_enabled,
    show_session,
)
from chat_lms_agent.state import ProfileState

SESSION_ID = "019ed3d3-b07d-7aa0-9722-40b75b22ba6f"


@pytest.fixture(autouse=True)
def _isolate_host_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Never discover the developer machine's real host home during tests.
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _profile(tmp_path: Path) -> ProfileState:
    return ProfileState(root=tmp_path / "profile", repo_root=_repo_root())


def _full_rollout(session_id: str = SESSION_ID) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": "2026-06-17T04:25:29Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": "C:\\ws",
                "originator": "Codex Desktop",
                "cli_version": "0.140.0",
                "git": {"branch": "master", "commit_hash": "abc1234"},
            },
        },
        {
            "timestamp": "2026-06-17T04:25:30Z",
            "type": "turn_context",
            "payload": {
                "model": "gpt-5.5",
                "cwd": "C:\\ws",
                "approval_policy": "never",
                "sandbox_policy": {"type": "danger-full-access"},
                "effort": "medium",
            },
        },
        {
            "timestamp": "2026-06-17T04:25:31Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "EBSS record please"},
        },
        {
            "timestamp": "2026-06-17T04:25:32Z",
            "type": "response_item",
            "payload": {"type": "reasoning", "summary": [], "encrypted_content": "opaque"},
        },
        {
            "timestamp": "2026-06-17T04:25:33Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "arguments": '{"cmd": "write-action apply"}',
                "call_id": "call_1",
            },
        },
        {
            "timestamp": "2026-06-17T04:25:34Z",
            "type": "response_item",
            "payload": {"type": "function_call_output", "call_id": "call_1", "output": "ok"},
        },
        {
            "timestamp": "2026-06-17T04:25:35Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "done", "phase": "final"},
        },
        {
            "timestamp": "2026-06-17T04:25:36Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 10,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 120,
                    },
                },
            },
        },
    ]


def _write_rollout(
    codex_home: Path,
    session_id: str,
    lines: list[dict[str, Any]],
    *,
    trailing_newline: bool = True,
) -> Path:
    day = codex_home / "sessions" / "2026" / "06" / "17"
    day.mkdir(parents=True, exist_ok=True)
    path = day / f"rollout-2026-06-17T13-25-26-{session_id}.jsonl"
    blob = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    if not trailing_newline and blob.endswith("\n"):
        blob = blob[:-1]
    _ = path.write_text(blob, encoding="utf-8")
    return path


def _records(profile: ProfileState, session_id: str = SESSION_ID) -> list[dict[str, Any]]:
    _code, payload = show_session(profile, session_id)
    records = payload["records"]
    assert isinstance(records, list)
    return [record for record in records if isinstance(record, dict)]


def _by_kind(records: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [record for record in records if record.get("kind") == kind]


def test_ingest_normalizes_every_event_type(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    _write_rollout(codex_home, SESSION_ID, _full_rollout())

    result = ingest_rollouts(profile, transcript_home=str(codex_home))

    assert result["status"] == "PASS"
    assert result["records_appended"] == 8
    records = _records(profile)
    prompt = _by_kind(records, "user_prompt")[0]
    assert prompt["text"] == "EBSS record please"
    reasoning = _by_kind(records, "reasoning")[0]
    assert reasoning["encrypted"] is True
    assert reasoning["text"] is None
    tool_call = _by_kind(records, "tool_call")[0]
    assert tool_call["tool_name"] == "shell"
    assert tool_call["call_id"] == "call_1"
    assert "write-action apply" in str(tool_call["tool_args"])
    assert _by_kind(records, "tool_output")[0]["call_id"] == "call_1"
    assert _by_kind(records, "agent_message")[-1]["text"] == "done"
    usage = _by_kind(records, "usage")[0]
    assert usage["tokens"] == {
        "input_tokens": 100,
        "cached_input_tokens": 10,
        "output_tokens": 20,
        "reasoning_output_tokens": 5,
        "total_tokens": 120,
    }
    turn = _by_kind(records, "turn_context")[0]
    assert turn["model"] == "gpt-5.5"
    assert turn["approval"] == "never"
    assert turn["sandbox"] == "danger-full-access"
    assert turn["effort"] == "medium"
    assert _by_kind(records, "session_meta")


def test_session_log_lands_in_private_state_dir(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    _write_rollout(codex_home, SESSION_ID, _full_rollout())

    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    expected = tmp_path / "profile" / ".chat-lms-state" / "session-logs" / f"{SESSION_ID}.jsonl"
    assert expected.exists()


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    _write_rollout(codex_home, SESSION_ID, _full_rollout())

    first = ingest_rollouts(profile, transcript_home=str(codex_home))
    second = ingest_rollouts(profile, transcript_home=str(codex_home))

    assert first["records_appended"] == 8
    assert second["records_appended"] == 0
    assert len(_records(profile)) == 8


def test_ingest_is_incremental(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    rollout = _full_rollout()
    _write_rollout(codex_home, SESSION_ID, rollout)
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    rollout.append(
        {
            "timestamp": "2026-06-17T04:25:40Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "second turn"},
        },
    )
    _write_rollout(codex_home, SESSION_ID, rollout)
    result = ingest_rollouts(profile, transcript_home=str(codex_home))

    assert result["records_appended"] == 1
    prompts = _by_kind(_records(profile), "user_prompt")
    assert [prompt["text"] for prompt in prompts] == ["EBSS record please", "second turn"]


def test_partial_last_line_is_not_consumed_until_complete(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    rollout = _full_rollout()
    _write_rollout(codex_home, SESSION_ID, rollout, trailing_newline=False)

    partial = ingest_rollouts(profile, transcript_home=str(codex_home))
    # Last line was still being written (no trailing newline) -> held back.
    assert partial["records_appended"] == 7

    _write_rollout(codex_home, SESSION_ID, rollout, trailing_newline=True)
    completed = ingest_rollouts(profile, transcript_home=str(codex_home))
    assert completed["records_appended"] == 1
    assert len(_records(profile)) == 8


def test_secrets_and_paths_are_redacted_on_disk(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    secret_assignment = "MY_" + "SECRET" + "=hunter2"
    windows_path = "C:\\Windows\\System32\\config"
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:34Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_9",
                "output": f"{secret_assignment} at {windows_path}",
            },
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)

    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    on_disk = (
        tmp_path / "profile" / ".chat-lms-state" / "session-logs" / f"{SESSION_ID}.jsonl"
    ).read_text(encoding="utf-8")
    assert "hunter2" not in on_disk
    assert "System32" not in on_disk
    assert "[redacted]" in on_disk


def test_learner_name_is_pseudonymized_on_disk_and_restored_on_show(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    learner = "민지"
    _write_privacy(tmp_path / "profile", learner)
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:31Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": f"{learner} 단어장 진도"},
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)

    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    on_disk = (
        tmp_path / "profile" / ".chat-lms-state" / "session-logs" / f"{SESSION_ID}.jsonl"
    ).read_text(encoding="utf-8")
    assert learner not in on_disk
    assert "[P:" in on_disk
    # Owner-facing show restores the real name via a pure local lookup.
    shown = _by_kind(_records(profile), "user_prompt")[0]
    assert learner in str(shown["text"])


def test_export_keeps_pseudonyms_unless_reveal(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    learner = "민지"
    _write_privacy(tmp_path / "profile", learner)
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:31Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": f"{learner} 진도"},
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    _safe_code, safe = export_session(profile, SESSION_ID)
    _reveal_code, revealed = export_session(profile, SESSION_ID, reveal=True)

    assert learner not in json.dumps(safe, ensure_ascii=False)
    assert learner in json.dumps(revealed, ensure_ascii=False)


def test_list_sessions_reports_counts(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    _write_rollout(codex_home, SESSION_ID, _full_rollout())
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    listing = list_sessions(profile)
    sessions = listing["sessions"]
    assert isinstance(sessions, list)
    assert listing["session_count"] == 1
    info = sessions[0]
    assert isinstance(info, dict)
    assert info["session_id"] == SESSION_ID
    assert info["model"] == "gpt-5.5"
    assert info["prompt_count"] == 1
    assert info["tool_count"] == 1
    assert info["error_count"] == 0


def test_error_count_detects_nonzero_exit(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:34Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_5",
                "output": "command failed with exit code: 1",
            },
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    info = list_sessions(profile)["sessions"]
    assert isinstance(info, list)
    first = info[0]
    assert isinstance(first, dict)
    assert first["error_count"] == 1


def test_disabled_ledger_skips_ingest(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    _write_rollout(codex_home, SESSION_ID, _full_rollout())

    assert is_enabled(profile) is True
    _ = set_enabled(profile, enabled=False)
    assert is_enabled(profile) is False
    result = ingest_rollouts(profile, transcript_home=str(codex_home))
    assert result["skipped"] == "disabled"
    session_file = tmp_path / "profile" / ".chat-lms-state" / "session-logs" / f"{SESSION_ID}.jsonl"
    assert not session_file.exists()

    _ = set_enabled(profile, enabled=True)
    again = ingest_rollouts(profile, transcript_home=str(codex_home))
    assert again["records_appended"] == 8


def test_automatic_locator_finds_isolated_teacher_home(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    isolated = profile.root / "codex-home"
    _write_rollout(isolated, SESSION_ID, _full_rollout())

    result = ingest_rollouts(profile)  # no explicit codex_home -> discovery

    assert result["status"] == "PASS"
    assert result["records_appended"] == 8


def test_missing_sessions_dir_is_safe(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    result = ingest_rollouts(profile, transcript_home=str(tmp_path / "empty"))
    assert result["status"] == "PASS"
    assert result["skipped"] == "no-sessions-dir"


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    day = codex_home / "sessions" / "2026" / "06" / "17"
    day.mkdir(parents=True, exist_ok=True)
    good = json.dumps(_full_rollout()[2], ensure_ascii=False)
    path = day / f"rollout-2026-06-17T13-25-26-{SESSION_ID}.jsonl"
    _ = path.write_text(f"{{not json\n{good}\n\n", encoding="utf-8")

    result = ingest_rollouts(profile, transcript_home=str(codex_home))

    assert result["status"] == "PASS"
    assert result["records_appended"] == 1


def test_lock_held_skips_without_duplicating(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    _write_rollout(codex_home, SESSION_ID, _full_rollout())
    logs_dir = tmp_path / "profile" / ".chat-lms-state" / "session-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    lock = logs_dir / "_ingest.lock"
    _ = lock.write_text("held", encoding="utf-8")

    result = ingest_rollouts(profile, transcript_home=str(codex_home))

    assert result["skipped"] == "locked"
    assert not (logs_dir / f"{SESSION_ID}.jsonl").exists()


def test_retention_prunes_oldest_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_ledger, "MAX_SESSION_FILES", 2)
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    for index in range(4):
        session_id = f"019ed3d3-b07d-7aa0-9722-00000000000{index}"
        _write_rollout(codex_home, session_id, _full_rollout(session_id))
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    logs_dir = tmp_path / "profile" / ".chat-lms-state" / "session-logs"
    remaining = list(logs_dir.glob("*.jsonl"))
    assert len(remaining) == 2


def test_retention_ranks_by_session_recency_not_file_mtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: when a backlog drains in budget-sized chunks the oldest
    # sessions are written last, so their log files have the newest mtime. A
    # file-mtime sort would then keep the oldest sessions and evict the newest.
    # Retention must rank by the session's own last activity timestamp.
    monkeypatch.setattr(session_ledger, "MAX_SESSION_FILES", 2)
    profile = _profile(tmp_path)
    logs_dir = profile.root / ".chat-lms-state" / "session-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # last_ts (true recency) and file mtime are deliberately inverted.
    plan = [
        ("newest", "2026-06-27T10:00:00Z", 1_000.0),  # newest session, OLDEST file
        ("middle", "2026-06-20T10:00:00Z", 2_000.0),
        ("oldest", "2026-06-01T10:00:00Z", 3_000.0),  # oldest session, NEWEST file
    ]
    sessions: dict[str, Any] = {}
    for stem, last_ts, mtime in plan:
        path = logs_dir / f"{stem}.jsonl"
        _ = path.write_text("{}\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
        sessions[stem] = {"session_id": stem, "last_ts": last_ts, "started_at": last_ts}

    session_ledger._prune_retention(profile, sessions)  # noqa: SLF001

    survivors = {path.stem for path in logs_dir.glob("*.jsonl")}
    assert survivors == {"newest", "middle"}
    assert "oldest" not in sessions


def test_credential_values_are_redacted_on_disk(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    creds = [
        "sk-" + "proj" + "ABCDEF1234567890XYZ",
        "Bearer " + "ab12cd34ef99ZZ",
        "AKIA" + "IOSFODNN7EXAMPLE",
        "gh" + "p_" + "A" * 24,
        "eyJ" + "abcdefgh.Zk9wYWlu.cccccccc",
        "\\\\fileserver\\share\\private\\roster.xlsx",
    ]
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:34Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "c1",
                "output": " ".join(creds),
            },
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    on_disk = (
        tmp_path / "profile" / ".chat-lms-state" / "session-logs" / f"{SESSION_ID}.jsonl"
    ).read_text(encoding="utf-8")
    for cred in creds:
        assert cred not in on_disk, cred
    assert "[redacted]" in on_disk


def test_custom_mcp_patch_and_search_tool_calls_are_captured(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:31Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "call_id": "c1",
                "name": "apply_patch",
                "input": "*** Begin Patch ... edit foo.py",
            },
        },
        {
            "timestamp": "2026-06-17T04:25:32Z",
            "type": "response_item",
            "payload": {"type": "custom_tool_call_output", "call_id": "c1", "output": "patched"},
        },
        {
            "timestamp": "2026-06-17T04:25:33Z",
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "call_id": "c2",
                "invocation": {
                    "server": "git_bash",
                    "tool": "run",
                    "arguments": {"command": "git status"},
                },
                "result": {"Ok": {"content": [{"type": "text", "text": "clean"}]}},
            },
        },
        {
            "timestamp": "2026-06-17T04:25:34Z",
            "type": "event_msg",
            "payload": {
                "type": "patch_apply_end",
                "call_id": "c3",
                "success": True,
                "stdout": "Success",
                "stderr": "",
                "changes": {"C:\\ws\\secret_dir\\a.py": {"type": "add", "content": "x"}},
            },
        },
        {
            "timestamp": "2026-06-17T04:25:35Z",
            "type": "response_item",
            "payload": {"type": "tool_search_call", "call_id": "c4", "arguments": {"query": "rg"}},
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)
    result = ingest_rollouts(profile, transcript_home=str(codex_home))

    assert result["records_appended"] == 5
    records = _records(profile)
    calls = _by_kind(records, "tool_call")
    names = {record["tool_name"] for record in calls}
    assert "apply_patch" in names
    assert "git_bash.run" in names
    assert "tool_search_call" in names
    custom = next(record for record in calls if record["tool_name"] == "apply_patch")
    assert "Begin Patch" in str(custom["tool_args"])
    mcp = next(record for record in calls if record["tool_name"] == "git_bash.run")
    assert "clean" in str(mcp["tool_output"])
    outputs = _by_kind(records, "tool_output")
    patch = next(record for record in outputs if record["tool_name"] == "apply_patch")
    on_disk = (
        tmp_path / "profile" / ".chat-lms-state" / "session-logs" / f"{SESSION_ID}.jsonl"
    ).read_text(encoding="utf-8")
    assert "secret_dir" not in on_disk  # absolute path in patch changes is redacted
    assert "Success" in str(patch["tool_output"])


def test_agent_reasoning_plaintext_is_captured(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:31Z",
            "type": "event_msg",
            "payload": {"type": "agent_reasoning", "text": "plan the EBSS write"},
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    reasoning = _by_kind(_records(profile), "reasoning")[0]
    assert reasoning["encrypted"] is False
    assert reasoning["text"] == "plan the EBSS write"


def test_unknown_event_type_is_captured_not_dropped(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:31Z",
            "type": "event_msg",
            "payload": {"type": "some_future_event", "detail": "novel"},
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)
    result = ingest_rollouts(profile, transcript_home=str(codex_home))

    assert result["records_appended"] == 1
    other = _by_kind(_records(profile), "other")[0]
    assert other["tool_name"] == "event:some_future_event"
    assert "novel" in str(other["text"])


def test_restore_applies_to_tool_output(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    learner = "민지"
    _write_privacy(tmp_path / "profile", learner)
    rollout = [
        {
            "timestamp": "2026-06-17T04:25:34Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "c1",
                "output": f"{learner} 점수 입력 완료",
            },
        },
    ]
    _write_rollout(codex_home, SESSION_ID, rollout)
    _ = ingest_rollouts(profile, transcript_home=str(codex_home))

    on_disk = (
        tmp_path / "profile" / ".chat-lms-state" / "session-logs" / f"{SESSION_ID}.jsonl"
    ).read_text(encoding="utf-8")
    assert learner not in on_disk
    shown = _by_kind(_records(profile), "tool_output")[0]
    assert learner in str(shown["tool_output"])


def test_ingest_never_raises_when_state_path_is_blocked(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    codex_home = tmp_path / "codex-home"
    _write_rollout(codex_home, SESSION_ID, _full_rollout())
    # Occupy the session-logs path with a FILE so mkdir inside the lock fails.
    state_dir = tmp_path / "profile" / ".chat-lms-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _ = (state_dir / "session-logs").write_text("blocker", encoding="utf-8")

    result = ingest_rollouts(profile, transcript_home=str(codex_home))  # must not raise

    assert result["status"] in {"PASS", "ERROR"}


def test_ingest_skips_when_profile_root_is_under_repo(tmp_path: Path) -> None:
    repo_root = _repo_root()
    profile = ProfileState(root=repo_root / "build" / "x", repo_root=repo_root)
    result = ingest_rollouts(profile, transcript_home=str(tmp_path / "codex-home"))
    assert result["skipped"] == "repo-root"
    assert not (repo_root / "build").exists()


def _write_privacy(root: Path, learner: str) -> None:
    state_dir = root / ".chat-lms-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _ = (state_dir / "privacy.json").write_text(
        json.dumps(
            {
                "schema_version": "privacy-v1",
                "entries": [{"match": learner, "kind": "plain", "mode": "reversible"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
