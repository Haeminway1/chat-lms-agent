from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.context import build_host_context
from chat_lms_agent.route_packs import load_route_packs
from chat_lms_agent.state import ProfileState


def _write_pack(root: Path, name: str, payload: dict[str, object]) -> None:
    packs_dir = root / ".chat-lms-state" / "routes"
    packs_dir.mkdir(parents=True, exist_ok=True)
    (packs_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _quiz_pack() -> dict[str, object]:
    return {
        "schema_version": "route-pack-v1",
        "id": "quiz-report",
        "bucket": "trigger",
        "summary": "퀴즈 리포트 라우트",
        "required_tokens": ["퀴즈", "리포트"],
        "first_command": "python -m chat_lms_agent academy-db query list --json",
        "then_command": "python -m chat_lms_agent academy-db query run --name learner-count --json",
        "fallback_command": "python -m chat_lms_agent doctor --json",
        "must_not": ["do not create a new HTML report for this request"],
        "time_budget_ms": 5000,
    }


def test_profile_route_pack_routes_prompt_without_code_change() -> None:
    # Given: a teacher-added route pack in the hermetic profile.
    profile_root = Path(os.environ["CHAT_LMS_AGENT_PROFILE_ROOT"])
    _write_pack(profile_root, "quiz-report.json", _quiz_pack())

    # When: a matching prompt arrives.
    stdin = json.dumps({"session_id": "s1", "prompt": "이번 주 퀴즈 리포트 정리해줘"})
    result = _run_cli(stdin, "hook", "user-prompt-submit", "--json")

    # Then: the pack route card is injected.
    assert result.returncode == 0, result.stdout
    context = _additional_context(result.stdout)
    route = context["prompt_route"]
    assert isinstance(route, dict)
    assert route["route_id"] == "quiz-report"
    assert route["source"] == "profile"
    assert "academy-db query list" in str(route["first_command"])


def test_invalid_pack_is_skipped_with_warning(tmp_path: Path) -> None:
    # Given: one valid and one malformed pack.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_pack(tmp_path / "profile", "quiz-report.json", _quiz_pack())
    packs_dir = tmp_path / "profile" / ".chat-lms-state" / "routes"
    (packs_dir / "broken.json").write_text("{not json", encoding="utf-8")
    (packs_dir / "wrong-bucket.json").write_text(
        json.dumps({"schema_version": "route-pack-v1", "id": "x", "bucket": "nope"}),
        encoding="utf-8",
    )

    # When: packs load.
    packs, warnings = load_route_packs(_repo_root(), profile)

    # Then: the valid profile pack survives (alongside repo defaults); the bad
    # ones are warned about, not fatal.
    pack_ids = {pack.pack_id for pack in packs}
    assert "quiz-report" in pack_ids
    assert "x" not in pack_ids
    assert len(warnings) == 2


def test_buckets_shape_hydration_listing(tmp_path: Path) -> None:
    # Given: an always-inject card and a listed-lazy pack.
    always = _quiz_pack()
    always["id"] = "daily-brief"
    always["bucket"] = "always_inject"
    always["required_tokens"] = []
    _write_pack(tmp_path / "profile", "daily-brief.json", always)
    lazy = _quiz_pack()
    lazy["id"] = "monthly-summary"
    lazy["bucket"] = "listed_lazy"
    _write_pack(tmp_path / "profile", "monthly-summary.json", lazy)

    # When: the full context builds.
    context = build_host_context(_repo_root(), str(tmp_path / "profile"), None)

    # Then: cards carry commands; listed entries carry ids and summaries only.
    section = context["route_packs"]
    assert isinstance(section, dict)
    cards = section["cards"]
    assert isinstance(cards, list)
    assert any(
        isinstance(card, dict) and card.get("route_id") == "daily-brief" for card in cards
    )
    listed = section["listed"]
    assert isinstance(listed, list)
    listed_entry = next(
        entry
        for entry in listed
        if isinstance(entry, dict) and entry.get("route_id") == "monthly-summary"
    )
    assert "first_command" not in listed_entry


def _additional_context(stdout: str) -> dict[str, object]:
    envelope = json.loads(stdout)
    hook_output = envelope["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    context = json.loads(hook_output["additionalContext"])
    assert isinstance(context, dict)
    return context


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
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
