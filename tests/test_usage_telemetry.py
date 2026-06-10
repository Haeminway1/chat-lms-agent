from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.state import ProfileState
from chat_lms_agent.usage_telemetry import record_surface_use, usage_counts


def test_surface_counts_accumulate_without_learner_data(tmp_path: Path) -> None:
    # Given: a profile.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())

    # When: surfaces are used.
    record_surface_use(profile, "route:lesson_wordbook_status")
    record_surface_use(profile, "route:lesson_wordbook_status")
    record_surface_use(profile, "block:attendance-summary")

    # Then: counts and timestamps only — no free text rides along.
    counts = usage_counts(profile)
    route_entry = counts["route:lesson_wordbook_status"]
    assert isinstance(route_entry, dict)
    assert route_entry["count"] == 2
    assert set(route_entry) == {"count", "last_used_at"}


def test_route_hits_are_counted_by_the_prompt_hook() -> None:
    # Given: the hermetic env profile.
    profile_root = Path(os.environ["CHAT_LMS_AGENT_PROFILE_ROOT"])

    # When: a wordbook-routed prompt arrives twice.
    stdin = json.dumps({"session_id": "s1", "prompt": "과외 가상학생 학생 단어 현황 보고"})
    first = _run_cli(stdin, "hook", "user-prompt-submit", "--json")
    second = _run_cli(stdin, "hook", "user-prompt-submit", "--json")

    # Then: the route usage is tallied in profile state.
    assert first.returncode == 0, first.stdout
    assert second.returncode == 0, second.stdout
    telemetry = json.loads(
        (profile_root / ".chat-lms-state" / "usage-telemetry.json").read_text(encoding="utf-8"),
    )
    assert telemetry["route:lesson_wordbook_status"]["count"] == 2


def test_closeout_nudges_promotion_candidates(tmp_path: Path) -> None:
    # Given: a draft block previewed three times (real usage signal).
    proposal = {
        "id": "quiz-summary",
        "label": "Quiz Summary",
        "summary": "퀴즈 요약 카드.",
        "render_contract": {"required_keys": ["title"]},
        "privacy_level": "class",
        "action_safety": {"requires_approval": True, "dry_run_default": True},
        "test_contract": {"command": "uv run pytest -q"},
        "reuse_review": {"checked_existing": [], "custom_build_justification": "new"},
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps({"title": "퀴즈"}), encoding="utf-8")
    scaffold = _run_cli(
        "",
        "side-panel",
        "block",
        "scaffold",
        "--from",
        str(proposal_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert scaffold.returncode == 0, scaffold.stdout
    for _ in range(3):
        preview = _run_cli(
            "",
            "side-panel",
            "block",
            "preview",
            "--id",
            "quiz-summary",
            "--sample",
            str(sample_path),
            "--profile-root",
            str(tmp_path),
            "--json",
        )
        assert preview.returncode == 0, preview.stdout

    # When: the session closes cleanly.
    closeout = _run_cli(
        "",
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    # Then: the block is suggested for promotion — advisory only, never auto.
    assert closeout.returncode == 0, closeout.stdout
    payload = json.loads(closeout.stdout)
    assert payload["status"] == "PASS"
    assert "quiz-summary" in payload["promotion_candidates"]


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
