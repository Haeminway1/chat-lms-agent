from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from chat_lms_agent.side_panel_design_systems import load_design_systems
from chat_lms_agent.state import ProfileState

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def test_design_system_resolution_profile_override_wins_and_bad_design_warns(
    tmp_path: Path,
) -> None:
    # Given: the repo default system plus a teacher profile override with the same id.
    profile_root = tmp_path / "profile"
    _write_design_system(profile_root, "toss-style", "Profile Toss", "프로필 맞춤형 토스 스타일")
    bad_dir = profile_root / ".chat-lms-state" / "design-systems" / "broken-style"
    bad_dir.mkdir(parents=True)
    (bad_dir / "DESIGN.md").write_text("# Broken\n\n## Identity\nToo short.\n", encoding="utf-8")

    # When: design systems are resolved with profile precedence.
    profile = ProfileState(root=profile_root, repo_root=_repo_root())
    systems, warnings = load_design_systems(_repo_root(), profile)

    # Then: the profile `toss-style` overrides the repo default and malformed files warn only.
    by_id = {system.system_id: system for system in systems}
    assert by_id["toss-style"].source == "profile"
    assert by_id["toss-style"].summary == "프로필 맞춤형 토스 스타일"
    assert by_id["toss-style"].design_path == bad_dir.parent / "toss-style" / "DESIGN.md"
    assert "broken-style/DESIGN.md: INVALID_DESIGN_SCHEMA" in warnings


def test_design_system_resolution_exposes_repo_default_without_profile() -> None:
    # Given/When: the repo default design systems are loaded.
    systems, warnings = load_design_systems(_repo_root(), None)

    # Then: Toss-style is available as repo data without profile state.
    by_id = {system.system_id: system for system in systems}
    assert warnings == []
    assert by_id["toss-style"].source == "repo"
    assert by_id["toss-style"].summary
    assert "Toss" in by_id["toss-style"].name


def test_design_systems_list_cli_returns_json_contract(tmp_path: Path) -> None:
    # Given: a profile override and one malformed profile design system.
    profile_root = tmp_path / "profile"
    _write_design_system(profile_root, "toss-style", "Profile Toss", "교사용 프로필 우선 스타일")
    bad_dir = profile_root / ".chat-lms-state" / "design-systems" / "bad-style"
    bad_dir.mkdir(parents=True)
    (bad_dir / "DESIGN.md").write_text("# Bad\n", encoding="utf-8")

    # When: the CLI lists design systems.
    result = _run_cli(
        "side-panel",
        "design",
        "systems",
        "list",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: JSON includes source/id/summary entries and warning text without leaking paths.
    assert result.returncode == 0, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "PASS"
    systems = _json_list(payload["systems"])
    toss = next(item for item in systems if _json_object(item)["id"] == "toss-style")
    toss_system = _json_object(toss)
    assert toss_system == {
        "id": "toss-style",
        "source": "profile",
        "summary": "교사용 프로필 우선 스타일",
    }
    warnings = _json_list(payload["warnings"])
    assert "bad-style/DESIGN.md: INVALID_DESIGN_SCHEMA" in warnings
    assert str(profile_root) not in result.stdout


def _write_design_system(profile_root: Path, system_id: str, title: str, summary: str) -> None:
    target = profile_root / ".chat-lms-state" / "design-systems" / system_id / "DESIGN.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"""# {title}

## Identity
Summary: {summary}
This profile design system keeps the lesson panel focused on teacher decisions.

## Color
Use one clear accent and neutral surfaces.

## Typography
Use Pretendard first with platform fallbacks.

## Spacing
Keep a mobile single-column rhythm.

## Components
Use compact panel blocks and avoid nested cards.

## Motion
Prefer short, restrained state changes.

## Voice
친절한 존댓말로 간결하게 안내한다.

## Accessibility
Preserve contrast, readable type, and touch targets.

## Anti-patterns
No horizontal carousels, dense tables, or decorative gradients.
""",
        encoding="utf-8",
    )


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


def _json_object(value: str | JsonValue) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(value)) if isinstance(value, str) else value
    assert isinstance(payload, dict)
    return payload


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value
