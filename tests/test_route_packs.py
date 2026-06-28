from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.context import build_host_context
from chat_lms_agent.route_packs import load_route_packs, match_pack_route, route_packs_context
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


def test_repo_record_class_route_matches_korean_entry_phrase() -> None:
    # Given: repo route packs including the record-class write workflow route.
    packs, warnings = load_route_packs(_repo_root())

    # When: a Korean class-entry prompt is matched.
    route = match_pack_route(packs, "오늘 수업 기록 기입하고 출석 숙제 진도 입력")

    # Then: the record-class route asks for roster resolution before apply.
    assert warnings == []
    assert route is not None
    assert route.pack_id == "record_class"
    assert "write-action roster" in route.first_command
    assert "write-action apply --id record-class" in route.then_command
    assert "write-action explain --id record-class" in route.fallback_command
    must_not_text = " ".join(route.must_not)
    assert "roster로 student_id를 먼저 확인" in must_not_text
    assert "roster가 돌려준 활성 학생 전원" in must_not_text
    assert "write-action session-gaps --class-code <code> --session-date <date>" in must_not_text


def test_repo_record_test_scores_route_matches_score_phrase() -> None:
    # Given: repo route packs including the composable test-score write workflow route.
    packs, warnings = load_route_packs(_repo_root())

    # When: a Korean score-entry prompt is matched.
    route = match_pack_route(packs, "오늘 시험 점수 채점 결과")

    # Then: the route asks for roster resolution before applying the score payload.
    assert warnings == []
    assert route is not None
    assert route.pack_id == "record_test_scores"
    assert "write-action roster" in route.first_command
    assert "write-action apply --id record-test-scores" in route.then_command
    assert "write-action explain --id record-test-scores" in route.fallback_command
    assert "scores[].student_id" in " ".join(route.must_not)


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


def test_session_start_command_index_includes_profile_trigger_first_command(
    tmp_path: Path,
) -> None:
    # Given: a teacher-authored trigger route in the profile.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_pack(tmp_path / "profile", "quiz-report.json", _quiz_pack())
    packs, warnings = load_route_packs(_repo_root(), profile)

    # When: SessionStart route-pack context is built.
    section = route_packs_context(packs)

    # Then: the profile trigger route carries its compact command index entry.
    assert warnings == []
    command_index = _json_list(section["command_index"])
    quiz_entry = next(
        entry
        for entry in command_index
        if isinstance(entry, dict) and entry.get("route_id") == "quiz-report"
    )
    assert quiz_entry["source"] == "profile"
    assert "academy-db query list" in str(quiz_entry["first_command"])
    assert "academy-db query run" in str(quiz_entry["then_command"])


def test_command_index_preserves_record_class_must_not_when_budgeted() -> None:
    # Given: repo trigger route packs.
    packs, warnings = load_route_packs(_repo_root())

    # When: route-pack context is built for SessionStart.
    section = route_packs_context(packs)

    # Then: record_class command discovery carries its non-droppable guardrails.
    assert warnings == []
    command_index = _json_list(section["command_index"])
    record_class = next(
        entry
        for entry in command_index
        if isinstance(entry, dict) and entry.get("route_id") == "record_class"
    )
    assert "write-action roster" in str(record_class["first_command"])
    must_not = record_class["must_not"]
    assert isinstance(must_not, list)
    must_not_text = " ".join(str(item) for item in must_not)
    assert "student_session_records" in must_not_text
    assert "session-gaps" in must_not_text


def test_command_index_profile_wins_order_is_deterministic(tmp_path: Path) -> None:
    # Given: a profile pack overrides a repo pack id.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    override = _quiz_pack()
    override["id"] = "record_class"
    override["first_command"] = "python -m chat_lms_agent profile-only --json"
    _write_pack(tmp_path / "profile", "record-class.json", override)
    packs, warnings = load_route_packs(_repo_root(), profile)

    # When: the compact command index is built.
    section = route_packs_context(packs)

    # Then: the profile entry wins and ordering stays stable.
    assert warnings == []
    command_index = [
        entry
        for entry in _json_list(section["command_index"])
        if isinstance(entry, dict) and "route_id" in entry
    ]
    ids = [entry["route_id"] for entry in command_index]
    expected_ids = sorted(
        ids,
        key=lambda route_id: (0 if route_id == "record_class" else 1, route_id),
    )
    assert ids == expected_ids
    record_class = next(entry for entry in command_index if entry["route_id"] == "record_class")
    assert record_class["source"] == "profile"
    assert record_class["first_command"] == "python -m chat_lms_agent profile-only --json"


def test_always_inject_cards_are_unchanged_when_command_index_is_added(
    tmp_path: Path,
) -> None:
    # Given: an always-inject pack.
    always = _quiz_pack()
    always["id"] = "daily-brief"
    always["bucket"] = "always_inject"
    always["required_tokens"] = []
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_pack(tmp_path / "profile", "daily-brief.json", always)
    packs, warnings = load_route_packs(_repo_root(), profile)

    # When: context is built.
    section = route_packs_context(packs)

    # Then: the card shape remains the full route card.
    assert warnings == []
    card = next(
        item
        for item in _json_list(section["cards"])
        if isinstance(item, dict) and item.get("route_id") == "daily-brief"
    )
    assert "fallback_command" in card
    assert "time_budget_ms" in card
    assert "command_index" in section


def test_command_index_dropped_entries_remain_listed_with_recovery_hint(
    tmp_path: Path,
) -> None:
    # Given: many oversized trigger packs force command-index truncation.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    for index in range(12):
        pack = _quiz_pack()
        pack["id"] = f"oversized-{index:02d}"
        pack["summary"] = "x" * 400
        pack["must_not"] = ["y" * 500]
        _write_pack(tmp_path / "profile", f"oversized-{index:02d}.json", pack)
    packs, warnings = load_route_packs(_repo_root(), profile)

    # When: a tiny command-index budget is used.
    section = route_packs_context(packs, command_index_budget=700)

    # Then: dropped packs are still listed with a recovery command.
    assert warnings == []
    listed = [
        entry for entry in _json_list(section["listed"]) if isinstance(entry, dict)
    ]
    assert any(entry.get("command_index_dropped") is True for entry in listed)
    dropped = next(entry for entry in listed if entry.get("command_index_dropped") is True)
    assert dropped["recovery_hint"] == "python -m chat_lms_agent agent-tools route list --json"


def _additional_context(stdout: str) -> dict[str, object]:
    envelope = json.loads(stdout)
    hook_output = envelope["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    context = json.loads(hook_output["additionalContext"])
    assert isinstance(context, dict)
    return context


def _json_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return value


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
