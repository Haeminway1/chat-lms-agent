from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.context import build_host_context
from chat_lms_agent.state import ProfileState, save_memory


def test_hook_stop_requires_memory_update_for_agent_tool_registry_change() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = _run_cli(
        repo_root,
        "hook",
        "stop",
        "--verify-memory",
        "--changed-files",
        "src/chat_lms_agent/agent_tools.py",
        "--json",
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "MEMORY_UPDATE_REQUIRED"
    assert "src/chat_lms_agent/agent_tools.py" in payload["changed_files"]


def test_hook_stop_allows_registry_change_with_memory_update_flag() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = _run_cli(
        repo_root,
        "hook",
        "stop",
        "--verify-memory",
        "--changed-files",
        "src/chat_lms_agent/agent_tools.py",
        "--memory-updated",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"


def test_levels_enforced_in_hydration() -> None:
    # Given: entries across levels, including a non-hydrating conversation_ref.
    repo_root = Path(__file__).resolve().parents[1]
    profile = ProfileState(
        root=Path(os.environ["CHAT_LMS_AGENT_PROFILE_ROOT"]),
        repo_root=repo_root,
    )
    save_memory(
        profile,
        [
            {
                "key": "ref:raw-1",
                "scope": "durable",
                "text": "offload pointer",
                "level": "conversation_ref",
            },
            {
                "key": "atom:fact-1",
                "scope": "durable",
                "text": "수업은 매주 화요일",
                "level": "atom",
            },
            {"key": "tool:legacy", "scope": "durable", "text": "레거시 항목"},
        ],
    )

    # When: the session-start context is built.
    context = build_host_context(repo_root, str(profile.root), None)

    # Then: hydrated_by_default=false levels stay out; others hydrate.
    memory_section = context["memory"]
    assert isinstance(memory_section, list)
    keys = {entry["key"] for entry in memory_section if isinstance(entry, dict) and "key" in entry}
    assert "atom:fact-1" in keys
    assert "tool:legacy" in keys
    assert "ref:raw-1" not in keys


def test_prompt_scoped_topk_recall() -> None:
    # Given: ten entries where only two mention the prompt topic.
    repo_root = Path(__file__).resolve().parents[1]
    profile = ProfileState(
        root=Path(os.environ["CHAT_LMS_AGENT_PROFILE_ROOT"]),
        repo_root=repo_root,
    )
    entries = [
        {"key": f"note:misc-{index}", "scope": "durable", "text": f"기타 메모 {index}"}
        for index in range(8)
    ]
    entries.append({"key": "note:wordbook-1", "scope": "durable", "text": "단어장 진도 기록"})
    entries.append({"key": "note:wordbook-2", "scope": "durable", "text": "단어장 복습 계획"})
    save_memory(profile, entries)

    # When: a prompt about the topic arrives.
    result = _run_cli(
        repo_root,
        "hook",
        "user-prompt-submit",
        "--json",
        stdin='{"session_id": "s1", "prompt": "단어장 진도 알려줘"}',
    )

    # Then: only the top-K matching entries ride along as recall.
    assert result.returncode == 0, result.stdout
    envelope = json.loads(result.stdout)
    context = json.loads(envelope["hookSpecificOutput"]["additionalContext"])
    recall = context["deltas"]["memory_recall"]
    recall_keys = [entry["key"] for entry in recall]
    assert "note:wordbook-1" in recall_keys
    assert "note:wordbook-2" in recall_keys
    assert len(recall) <= 5


def test_upsert_write_cap() -> None:
    # Given: an oversized memory text.
    repo_root = Path(__file__).resolve().parents[1]
    oversized = "긴 텍스트 " * 500

    # When: the upsert is attempted.
    result = _run_cli(
        repo_root,
        "memory",
        "upsert",
        "--key",
        "note:big",
        "--scope",
        "durable",
        "--text",
        oversized,
        "--json",
    )

    # Then: the write is rejected with an explicit size budget message.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "MEMORY_TEXT_TOO_LARGE"
    assert "/2000" in payload["message"]


def _run_cli(
    repo_root: Path,
    *args: str,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
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
