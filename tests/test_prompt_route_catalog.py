from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent import prompt_routes
from chat_lms_agent.state import JsonValue, ProfileState


def test_prompt_submit_weak_signal_no_match_injects_route_catalog() -> None:
    # Given: a panel-ish request that no route pack should match.
    stdin = json.dumps({"session_id": "s1", "prompt": "수업 화면 보여줘"})

    # When: the prompt-submit hook emits its delta context.
    result = _run_cli(stdin, "hook", "user-prompt-submit", "--json")

    # Then: the model receives the compact route catalog instead of bare deltas.
    assert result.returncode == 0, result.stdout
    context = _additional_context(result.stdout)
    catalog = context["route_catalog"]
    assert isinstance(catalog, dict)
    assert "instruction" in catalog
    assert any(
        isinstance(card, dict) and card.get("route_id") == "lesson_wordbook_status"
        for card in catalog["cards"]
    )
    assert "prompt_route" not in context


def test_prompt_submit_without_weak_signal_omits_route_catalog() -> None:
    # Given: an unrelated courtesy prompt with no route and no weak panel signal.
    stdin = json.dumps({"session_id": "s1", "prompt": "고마워"})

    # When: the prompt-submit hook emits its delta context.
    result = _run_cli(stdin, "hook", "user-prompt-submit", "--json")

    # Then: weak-signal gating keeps the hook context small.
    assert result.returncode == 0, result.stdout
    context = _additional_context(result.stdout)
    assert "route_catalog" not in context
    assert "prompt_route" not in context


def test_prompt_check_no_match_always_includes_route_catalog(
    tmp_path: Path,
) -> None:
    # Given: a non-matching prompt.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())

    # When: prompt-check evaluates it.
    payload = prompt_routes.prompt_check_payload("고마워", _repo_root(), profile)

    # Then: prompt-check still includes the catalog for semantic mapping.
    assert payload["status"] == "NO_MATCH"
    catalog = payload["route_catalog"]
    assert isinstance(catalog, dict)
    assert "instruction" in catalog
    assert any(
        isinstance(card, dict) and card.get("route_id") == "lesson_wordbook_status"
        for card in catalog["cards"]
    )


def test_route_catalog_respects_byte_ceiling_with_truncation_marker(
    tmp_path: Path,
) -> None:
    # Given: enough profile packs to exceed the compact catalog ceiling.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    for index in range(60):
        _write_pack(
            profile.root,
            f"extra-{index}.json",
            _route_pack_v2(pack_id=f"extra-{index}", token=f"token-{index}"),
        )

    # When: prompt-check builds the NO_MATCH route catalog.
    payload = prompt_routes.prompt_check_payload("고마워", _repo_root(), profile)

    # Then: the catalog remains byte-capped and ends with an explicit marker.
    catalog = payload["route_catalog"]
    assert isinstance(catalog, dict)
    blob = json.dumps(catalog, ensure_ascii=False, sort_keys=True).encode("utf-8")
    assert len(blob) <= prompt_routes.ROUTE_CATALOG_BYTE_CEILING
    marker = catalog["cards"][-1]
    assert isinstance(marker, dict)
    assert marker["truncated"] is True
    omitted = marker["omitted"]
    assert isinstance(omitted, int)
    assert omitted > 0


def _additional_context(stdout: str) -> dict[str, JsonValue]:
    envelope = json.loads(stdout)
    hook_output = envelope["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    raw_context = hook_output["additionalContext"]
    assert isinstance(raw_context, str)
    context = json.loads(raw_context)
    assert isinstance(context, dict)
    return context


def _route_pack_v2(*, pack_id: str, token: str) -> dict[str, JsonValue]:
    return {
        "schema_version": "route-pack-v2",
        "id": pack_id,
        "bucket": "trigger",
        "summary": f"extra route {pack_id}",
        "required_tokens": [],
        "any_tokens": [token],
        "first_command": (
            "python -m chat_lms_agent side-panel wordbook open-plan "
            "--student <student> --profile-root <root> --json"
        ),
        "then_command": (
            "python -m chat_lms_agent side-panel wordbook ensure-server "
            "--profile-root <root> --json"
        ),
        "fallback_command": "python -m chat_lms_agent doctor --json",
        "must_not": ["do not create a new HTML report"],
        "time_budget_ms": 5000,
    }


def _write_pack(root: Path, name: str, payload: dict[str, JsonValue]) -> None:
    packs_dir = root / ".chat-lms-state" / "routes"
    packs_dir.mkdir(parents=True, exist_ok=True)
    (packs_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


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
