from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent import prompt_routes
from chat_lms_agent.route_packs import load_route_packs, match_pack_route
from chat_lms_agent.state import JsonValue, ProfileState


def test_route_pack_v2_parsing_accepts_any_tokens_and_preserves_v1(
    tmp_path: Path,
) -> None:
    # Given: v2 trigger packs using alias tokens and an existing v1 pack.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_pack(
        profile.root,
        "alias-only.json",
        _route_pack_v2(required=(), any_tokens=("수업준비",)),
    )
    _write_pack(
        profile.root,
        "combined.json",
        _route_pack_v2(pack_id="combined", required=("수업",), any_tokens=("보조패널",)),
    )
    _write_pack(profile.root, "legacy.json", _route_pack_v1())

    # When: route packs load.
    packs, warnings = load_route_packs(_repo_root(), profile)

    # Then: v2 any_tokens are parsed and v1 keeps an empty alias list.
    assert warnings == []
    by_id = {pack.pack_id: pack for pack in packs}
    assert by_id["alias-only"].schema_version == "route-pack-v2"
    assert by_id["alias-only"].required_tokens == ()
    assert by_id["alias-only"].any_tokens == ("수업준비",)
    assert by_id["combined"].required_tokens == ("수업",)
    assert by_id["combined"].any_tokens == ("보조패널",)
    assert by_id["legacy-v1"].required_tokens == ("퀴즈",)
    assert by_id["legacy-v1"].any_tokens == ()
    assert by_id["legacy-v1"].schema_version == "route-pack-v1"


def test_route_pack_v2_trigger_requires_required_or_any_tokens(tmp_path: Path) -> None:
    # Given: a v2 trigger pack with neither required nor alias tokens.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_pack(profile.root, "broken.json", _route_pack_v2(required=(), any_tokens=()))

    # When: route packs load.
    packs, warnings = load_route_packs(_repo_root(), profile)

    # Then: the invalid pack is skipped with a validation warning.
    assert all(pack.pack_id != "alias-only" for pack in packs)
    assert warnings == ["broken.json: TRIGGER_REQUIRES_TOKENS"]


def test_route_pack_v2_matching_uses_required_and_any_token_semantics(
    tmp_path: Path,
) -> None:
    # Given: v2 packs for alias-only and combined required+alias matching.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_pack(
        profile.root,
        "alias-only.json",
        _route_pack_v2(required=(), any_tokens=("수업준비",)),
    )
    _write_pack(
        profile.root,
        "combined.json",
        _route_pack_v2(
            pack_id="combined",
            required=("수업",),
            any_tokens=("보조 패널", "lesson panel"),
        ),
    )
    packs, warnings = load_route_packs(_repo_root(), profile)

    # When/Then: alias-only OR, combined AND+OR, and multi-word tokens match.
    assert warnings == []
    alias_match = match_pack_route(packs, "수업준비 해줘")
    assert alias_match is not None
    assert alias_match.pack_id == "alias-only"
    combined_korean = match_pack_route(packs, "오늘 수업 보조 패널 열어줘")
    assert combined_korean is not None
    assert combined_korean.pack_id == "combined"
    combined_english = match_pack_route(packs, "open the 수업 lesson panel")
    assert combined_english is not None
    assert combined_english.pack_id == "combined"
    assert match_pack_route(packs, "보조 패널만 열어줘") is None


def test_prompt_route_resolver_and_prompt_check_match_profile_pack(
    tmp_path: Path,
) -> None:
    # Given: a tmp profile v2 pack that matches a lesson-prep alias.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_pack(profile.root, "lesson.json", _route_pack_v2(required=(), any_tokens=("수업준비",)))

    # When: the hook-equivalent resolver and prompt-check process the prompt.
    resolved = prompt_routes.resolve_prompt_route("수업준비 해줘", _repo_root(), profile)
    payload = prompt_routes.prompt_check_payload("수업준비 해줘", _repo_root(), profile)

    # Then: both surfaces report the same pack route id.
    assert resolved is not None
    assert resolved.route_id == "alias-only"
    route = payload["route"]
    assert isinstance(route, dict)
    assert route["route_id"] == resolved.route_id
    assert payload["status"] == "PASS"


def test_prompt_route_resolver_and_prompt_check_match_builtin_wordbook() -> None:
    # Given: a builtin wordbook prompt with a student hint.
    prompt = "가상학생 단어 html 패널 열어줘"

    # When: the hook-equivalent resolver and prompt-check process the prompt.
    resolved = prompt_routes.resolve_prompt_route(prompt, _repo_root(), None)
    payload = prompt_routes.prompt_check_payload(prompt, _repo_root(), None)

    # Then: both surfaces preserve the builtin wordbook route behavior.
    assert resolved is not None
    assert resolved.route_id == "lesson_wordbook_status"
    assert resolved.student_hint == "가상학생"
    route = payload["route"]
    assert isinstance(route, dict)
    assert route["route_id"] == resolved.route_id
    assert payload["student_hint"] == "가상학생"


def test_prompt_check_cli_matches_profile_pack(tmp_path: Path) -> None:
    # Given: a tmp profile v2 pack that matches a lesson-prep alias.
    profile_root = tmp_path / "profile"
    _write_pack(profile_root, "lesson.json", _route_pack_v2(required=(), any_tokens=("수업준비",)))

    # When: the public prompt-check CLI runs with that profile.
    result = _run_cli(
        "agent-tools",
        "prompt-check",
        "--prompt",
        "수업준비 해줘",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: prompt-check exits successfully with the profile pack route card.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["route"]["route_id"] == "alias-only"
    assert payload["route"]["schema_version"] == "route-pack-v2"


def _route_pack_v1() -> dict[str, JsonValue]:
    return {
        "schema_version": "route-pack-v1",
        "id": "legacy-v1",
        "bucket": "trigger",
        "summary": "legacy route",
        "required_tokens": ["퀴즈"],
        "first_command": "python -m chat_lms_agent doctor --json",
        "then_command": "python -m chat_lms_agent doctor --json",
        "fallback_command": "python -m chat_lms_agent doctor --json",
        "must_not": ["do not create a new HTML report for this request"],
        "time_budget_ms": 5000,
    }


def _route_pack_v2(
    *,
    pack_id: str = "alias-only",
    required: tuple[str, ...],
    any_tokens: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "schema_version": "route-pack-v2",
        "id": pack_id,
        "bucket": "trigger",
        "summary": "wordbook alias route",
        "required_tokens": list(required),
        "any_tokens": list(any_tokens),
        "first_command": "python -m chat_lms_agent side-panel wordbook open-plan --json",
        "then_command": "python -m chat_lms_agent side-panel wordbook ensure-server --json",
        "fallback_command": "python -m chat_lms_agent doctor --json",
        "must_not": ["do not create a new HTML report for this request"],
        "time_budget_ms": 5000,
    }


def _write_pack(root: Path, name: str, payload: dict[str, JsonValue]) -> None:
    packs_dir = root / ".chat-lms-state" / "routes"
    packs_dir.mkdir(parents=True, exist_ok=True)
    (packs_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )
