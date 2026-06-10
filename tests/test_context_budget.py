from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.context import (
    APPLIED_REDUCTIONS,
    CONTEXT_EVENT_BYTE_CEILING,
    CONTEXT_SECTION_BYTE_CEILINGS,
    build_host_context,
)
from chat_lms_agent.journal import write_trace
from chat_lms_agent.state import ProfileState, save_memory


def test_payload_is_deterministic(tmp_path: Path) -> None:
    # Given: identical inputs.
    first = build_host_context(_repo_root(), str(tmp_path / "p"), None)
    second = build_host_context(_repo_root(), str(tmp_path / "p"), None)

    # Then: the serialized payload is byte-identical (prompt-cache friendly).
    assert _blob(first) == _blob(second)


def test_payload_stable_across_journal_growth(tmp_path: Path) -> None:
    # Given: a baseline payload.
    root = tmp_path / "p"
    before = _blob(build_host_context(_repo_root(), str(root), None))

    # When: a trace record is appended.
    profile = ProfileState(root=root, repo_root=_repo_root())
    _ = write_trace(profile, "test_event", "volatility probe")

    # Then: the hydration payload does not change.
    after = _blob(build_host_context(_repo_root(), str(root), None))
    assert before == after


def test_empty_profile_within_event_ceiling(tmp_path: Path) -> None:
    # Given: an empty profile.
    context = build_host_context(_repo_root(), str(tmp_path / "p"), None)

    # Then: the full session-start payload fits the pinned ceiling.
    assert CONTEXT_EVENT_BYTE_CEILING == 10_000
    assert len(_blob(context)) <= CONTEXT_EVENT_BYTE_CEILING


def test_section_ceilings_enforced(tmp_path: Path) -> None:
    # Given: the pinned per-section budgets imported from production code.
    context = build_host_context(_repo_root(), str(tmp_path / "p"), None)

    # Then: every budgeted section is inside its ceiling.
    assert "memory" in CONTEXT_SECTION_BYTE_CEILINGS
    assert "oss_reference_registry" in CONTEXT_SECTION_BYTE_CEILINGS
    for key, ceiling in CONTEXT_SECTION_BYTE_CEILINGS.items():
        assert len(_blob(context.get(key))) <= ceiling, key


def test_memory_section_truncates_at_budget(tmp_path: Path) -> None:
    # Given: fifty oversized memory entries.
    root = tmp_path / "p"
    profile = ProfileState(root=root, repo_root=_repo_root())
    save_memory(
        profile,
        [
            {
                "key": f"tool:sample-{index}",
                "scope": "durable",
                "text": "수업 단어장 도구 사용 기록 " * 8,
            }
            for index in range(50)
        ],
    )

    # When: the full context is built.
    context = build_host_context(_repo_root(), str(root), None)

    # Then: the memory section respects its budget with an explicit marker.
    memory_section = context["memory"]
    assert isinstance(memory_section, list)
    assert len(_blob(memory_section)) <= CONTEXT_SECTION_BYTE_CEILINGS["memory"]
    marker = memory_section[-1]
    assert isinstance(marker, dict)
    assert marker["truncated"] is True
    omitted = marker["omitted"]
    assert isinstance(omitted, int)
    assert omitted > 0
    assert len(_blob(context)) <= 23_000


def test_applied_reductions_are_pinned() -> None:
    # Then: every diet step is recorded so silent regressions fail loudly.
    steps = {entry["step"] for entry in APPLIED_REDUCTIONS}
    assert {"journal_counts_removed", "event_tiering", "memory_section_budget"} <= steps


def test_user_prompt_submit_emits_route_and_delta_only() -> None:
    # Given: a wordbook prompt in a fresh hermetic profile.
    stdin = json.dumps(
        {"session_id": "s1", "prompt": "과외 가상학생 학생 단어 현황 보고"},
    )

    # When: the prompt-submit hook fires.
    result = _run_hook_cli(stdin, "hook", "user-prompt-submit", "--json")

    # Then: only the route card and actionable deltas are injected — no
    # repeated static sections.
    assert result.returncode == 0, result.stdout
    context = _additional_context(result.stdout)
    assert "prompt_route" in context
    assert "deltas" in context
    assert "memory" not in context
    assert "oss_reference_registry" not in context
    assert "agent_tools" not in context
    assert "side_panel" not in context


def test_post_tool_use_emits_only_on_obligation() -> None:
    # Given: a tool result with no obligation-triggering changed files.
    result = _run_hook_cli('{"session_id": "s1"}', "hook", "post-tool-use", "--json")

    # Then: no context is re-injected.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload == {"status": "PASS"}


def _blob(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _additional_context(stdout: str) -> dict[str, object]:
    envelope = json.loads(stdout)
    hook_output = envelope["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    context = json.loads(hook_output["additionalContext"])
    assert isinstance(context, dict)
    return context


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
