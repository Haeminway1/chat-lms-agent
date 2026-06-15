from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from chat_lms_agent import side_panel_design_generate as generate_module
from chat_lms_agent.side_panel_blocks import active_profile_blocks, open_block_ids
from chat_lms_agent.side_panel_design_generate import (
    DesignGenerateRequest,
    EngineSuccess,
    GenerationContext,
    generate_side_panel_design,
    register_design_engine_for_tests,
    reset_design_engines_for_tests,
)
from chat_lms_agent.state import ProfileState

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@pytest.fixture(autouse=True)
def _reset_design_engine_registry() -> None:
    reset_design_engines_for_tests()


def test_design_generate_composes_context_quarantines_and_reports_lint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingFakeEngine:
        engine_id = "fake"

        def __init__(self) -> None:
            self.contexts: list[GenerationContext] = []

        def generate(self, context: GenerationContext) -> EngineSuccess:
            self.contexts.append(context)
            return EngineSuccess(artifact_html=_compliant_html("round-one"), engine_notes="fixture")

    fake = RecordingFakeEngine()
    register_design_engine_for_tests(fake)
    monkeypatch.setattr(generate_module, "side_panel_design_lint", _pass_lint)
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())

    # Given: a deterministic fake engine and a tmp profile outside the repository.
    request = DesignGenerateRequest(
        view="learner_detail",
        modes=("panel", "fullscreen"),
        design_system_id="toss-style",
        brief="학생 상세 화면은 교사가 바로 행동할 수 있게 구성한다.",
        engine_id="fake",
    )

    # When: the design generation pipeline runs.
    code, payload = generate_side_panel_design(profile, request)

    # Then: one composed context is sent to the engine and the draft is quarantined.
    assert code == 0
    assert payload["status"] == "PASS"
    assert len(fake.contexts) == 1
    context = fake.contexts[0]
    assert "# Toss-Style Side Panel Design System" in context.design_markdown
    assert '"schema_version": "display-spec-v1"' in context.display_spec_json
    assert '"view_id": "learner_detail"' in context.view_payload_schema_json
    assert "D3_FIXTURE_LEARNER_DETAIL_SUMMARY" in context.synthetic_fixture_json
    assert "single offline HTML file" in context.prompt
    assert "fetch from relative /api/" in context.prompt
    assert "registered side-panel blocks only" in context.prompt
    assert 'meta name="side-panel-modes"' in context.prompt
    assert "light and dark themes" in context.prompt

    draft = _json_object(payload["draft"])
    assert draft["lifecycle_state"] == "draft"
    artifact_path = Path(_json_string(draft["artifact_path"]))
    preview_path = Path(_json_string(payload["preview_path"]))
    assert artifact_path == preview_path
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == _compliant_html("round-one")
    assert artifact_path.resolve().is_relative_to(profile.root.resolve())
    assert not artifact_path.resolve().is_relative_to(_repo_root().resolve())
    assert active_profile_blocks(profile) == []
    assert _json_string(draft["block_id"]) in open_block_ids(profile)

    verdicts = _json_object(payload["verdicts"])
    lint = _json_object(verdicts["lint"])
    assert lint["status"] == "PASS"
    evidence = _json_list(payload["evidence_trail"])
    assert len(evidence) == 1
    assert _json_object(evidence[0])["round"] == 1


def test_design_generate_keeps_profiles_and_design_systems_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingFakeEngine:
        engine_id = "fake"

        def __init__(self) -> None:
            self.contexts: list[GenerationContext] = []

        def generate(self, context: GenerationContext) -> EngineSuccess:
            self.contexts.append(context)
            marker = (
                "profile-a"
                if "Alpha profile system" in context.design_markdown
                else "profile-b"
            )
            return EngineSuccess(artifact_html=_compliant_html(marker), engine_notes=marker)

    fake = RecordingFakeEngine()
    register_design_engine_for_tests(fake)
    monkeypatch.setattr(generate_module, "side_panel_design_lint", _pass_lint)
    profile_a = ProfileState(root=tmp_path / "profile-a", repo_root=_repo_root())
    profile_b = ProfileState(root=tmp_path / "profile-b", repo_root=_repo_root())
    _write_design_system(profile_a.root, "toss-style", "Alpha profile system")
    _write_design_system(profile_b.root, "toss-style", "Beta profile system")
    request = DesignGenerateRequest(
        view="learner_detail",
        modes=("panel",),
        design_system_id="toss-style",
        brief=None,
        engine_id="fake",
    )

    # Given: two profiles override the same design-system id with different DESIGN.md files.
    code_a, payload_a = generate_side_panel_design(profile_a, request)
    code_b, payload_b = generate_side_panel_design(profile_b, request)

    # Then: each profile gets its own quarantined draft and no artifact is written in the repo.
    assert (code_a, code_b) == (0, 0)
    path_a = Path(_json_string(_json_object(payload_a["draft"])["artifact_path"]))
    path_b = Path(_json_string(_json_object(payload_b["draft"])["artifact_path"]))
    assert path_a.exists()
    assert path_b.exists()
    assert path_a != path_b
    assert path_a.read_text(encoding="utf-8") == _compliant_html("profile-a")
    assert path_b.read_text(encoding="utf-8") == _compliant_html("profile-b")
    assert path_a.resolve().is_relative_to(profile_a.root.resolve())
    assert path_b.resolve().is_relative_to(profile_b.root.resolve())
    assert not path_a.resolve().is_relative_to(_repo_root().resolve())
    assert not path_b.resolve().is_relative_to(_repo_root().resolve())
    assert "Alpha profile system" in fake.contexts[0].design_markdown
    assert "Beta profile system" in fake.contexts[1].design_markdown


def test_design_generate_defaults_to_codex_and_blocks_without_cli(tmp_path: Path) -> None:
    # Given: PATH contains no codex executable.
    result = _run_cli(
        "side-panel",
        "design",
        "generate",
        "--view",
        "learner_detail",
        "--profile-root",
        str(tmp_path / "profile"),
        "--json",
        env_extra={"PATH": ""},
    )

    # When/Then: the default engine is codex and the missing CLI blocks with an auth hint.
    assert result.returncode == 5, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["engine"] == "codex"
    assert payload["error_code"] == "CODEX_CLI_NOT_FOUND"
    assert "no API key is needed" in _json_string(payload["hint"])


def test_design_generate_open_design_blocks_when_local_tool_is_absent(tmp_path: Path) -> None:
    # Given: neither the local daemon env var nor od CLI is available.
    result = _run_cli(
        "side-panel",
        "design",
        "generate",
        "--view",
        "learner_detail",
        "--engine",
        "open-design",
        "--profile-root",
        str(tmp_path / "profile"),
        "--json",
        env_extra={"PATH": "", "CHAT_LMS_OPEN_DESIGN_DAEMON": ""},
    )

    # When/Then: open-design blocks locally without trying any remote endpoint.
    assert result.returncode == 5, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["engine"] == "open-design"
    assert payload["error_code"] == "OPEN_DESIGN_NOT_INSTALLED"
    assert "pinned SHA recorded in docs/oss-reference-registry.md" in _json_string(
        payload["install_hint"],
    )


def test_design_generate_open_design_rejects_non_open_design_od_on_path(tmp_path: Path) -> None:
    # Given: PATH contains an executable named od that is not the open-design CLI.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_od(fake_bin)

    # When: open-design generation probes the local environment.
    result = _run_cli(
        "side-panel",
        "design",
        "generate",
        "--view",
        "learner_detail",
        "--engine",
        "open-design",
        "--profile-root",
        str(tmp_path / "profile"),
        "--json",
        env_extra={"PATH": str(fake_bin), "CHAT_LMS_OPEN_DESIGN_DAEMON": ""},
    )

    # Then: the coreutils-style od is ignored and the typed install hint is returned.
    assert result.returncode == 5, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["engine"] == "open-design"
    assert payload["error_code"] == "OPEN_DESIGN_NOT_INSTALLED"
    assert "pinned SHA recorded in docs/oss-reference-registry.md" in _json_string(
        payload["install_hint"],
    )


def test_design_generate_refines_once_when_round_one_has_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingFakeEngine:
        engine_id = "fake"

        def __init__(self) -> None:
            self.contexts: list[GenerationContext] = []

        def generate(self, context: GenerationContext) -> EngineSuccess:
            self.contexts.append(context)
            return EngineSuccess(
                artifact_html=_compliant_html(f"round-{len(self.contexts)}"),
                engine_notes="fixture",
            )

    fake = RecordingFakeEngine()
    register_design_engine_for_tests(fake)
    monkeypatch.setattr(generate_module, "side_panel_design_lint", _findings_lint)
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    request = DesignGenerateRequest(
        view="learner_detail",
        modes=("panel",),
        design_system_id="toss-style",
        brief=None,
        engine_id="fake",
    )

    # Given: round-one checks report machine-readable findings.
    code, payload = generate_side_panel_design(profile, request)

    # Then: the same engine is re-prompted exactly once and checks are re-run.
    assert code == 0
    assert len(fake.contexts) == 2
    assert "fix these detector findings" in fake.contexts[1].prompt
    assert "card_nesting" in fake.contexts[1].prompt
    refinement = _json_object(payload["refinement"])
    assert refinement["iterations"] == 1
    evidence = _json_list(payload["evidence_trail"])
    assert [item["round"] for item in map(_json_object, evidence)] == [1, 2]
    preview_html = Path(_json_string(payload["preview_path"])).read_text(encoding="utf-8")
    assert preview_html == _compliant_html("round-2")


def test_design_generate_skips_refinement_when_round_one_has_zero_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingFakeEngine:
        engine_id = "fake"

        def __init__(self) -> None:
            self.contexts: list[GenerationContext] = []

        def generate(self, context: GenerationContext) -> EngineSuccess:
            self.contexts.append(context)
            return EngineSuccess(artifact_html=_compliant_html("round-one"), engine_notes="fixture")

    fake = RecordingFakeEngine()
    register_design_engine_for_tests(fake)
    monkeypatch.setattr(generate_module, "side_panel_design_lint", _pass_lint)
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    request = DesignGenerateRequest(
        view="learner_detail",
        modes=("panel",),
        design_system_id="toss-style",
        brief=None,
        engine_id="fake",
    )

    # Given: round-one checks have no findings.
    code, payload = generate_side_panel_design(profile, request)

    # Then: no second engine call is made.
    assert code == 0
    assert len(fake.contexts) == 1
    assert _json_object(payload["refinement"])["iterations"] == 0
    assert len(_json_list(payload["evidence_trail"])) == 1


def _pass_lint(artifact_path: Path, mode: str) -> tuple[int, dict[str, JsonValue]]:
    return (
        0,
        {
            "artifact": str(artifact_path),
            "mode": mode,
            "status": "PASS",
            "errors": [],
            "warnings": [],
            "advisory": {"impeccable": {"status": "PASS", "findings": []}},
        },
    )


def _findings_lint(artifact_path: Path, mode: str) -> tuple[int, dict[str, JsonValue]]:
    _ = artifact_path
    return (
        0,
        {
            "mode": mode,
            "status": "PASS",
            "errors": [],
            "warnings": [],
            "advisory": {
                "impeccable": {
                    "status": "FINDINGS",
                    "findings": [
                        {
                            "rule": "card_nesting",
                            "message": "Avoid card nesting in the side panel.",
                        },
                    ],
                },
            },
        },
    )


def _compliant_html(marker: str) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="side-panel-modes" content="panel fullscreen">
  <style>
    :root {{
      --sp-accent: #3182F6;
      --sp-fontSize: 15px;
      --sp-density: comfy;
      --sp-round: soft;
      --sp-theme: light;
      color-scheme: light;
      font-family: Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    [data-theme="dark"] {{
      --sp-theme: dark;
      color-scheme: dark;
    }}
    html, body {{ margin: 0; overflow-x: hidden; }}
    .side-panel-shell {{ max-width: 100%; width: min(100%, 372px); }}
    @media (min-width: 1024px) {{
      .side-panel-shell {{ width: min(100%, 1120px); }}
    }}
  </style>
</head>
<body>
  <main class="side-panel-shell" data-theme="light">
    <section data-marker="{marker}"></section>
  </main>
  <script>
    fetch('/api/lesson-panel').then((response) => response.json()).then(() => undefined);
  </script>
</body>
</html>
"""


def _write_design_system(profile_root: Path, system_id: str, summary: str) -> None:
    target = profile_root / ".chat-lms-state" / "design-systems" / system_id / "DESIGN.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"""# Profile Design

## Identity
Summary: {summary}
Teacher-owned design system for generated side-panel drafts.

## Color
Use one clear accent.

## Typography
Use Pretendard first.

## Spacing
Prefer compact mobile rhythm.

## Components
Use registered blocks only.

## Motion
Keep motion restrained.

## Voice
친절한 존댓말로 안내한다.

## Accessibility
Keep contrast and touch targets clear.

## Anti-patterns
No nested cards, horizontal carousels, or decorative gradients.
""",
        encoding="utf-8",
    )


def _run_cli(
    *args: str,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    if env_extra is not None:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )


def _write_fake_od(fake_bin: Path) -> None:
    posix_od = fake_bin / "od"
    posix_od.write_text("#!/bin/sh\necho 'od (GNU coreutils) 9.5' >&2\nexit 1\n", encoding="utf-8")
    posix_od.chmod(0o755)
    windows_od = fake_bin / "od.cmd"
    windows_od.write_text(
        "@echo off\necho od (GNU coreutils) 9.5 1>&2\nexit /b 1\n",
        encoding="utf-8",
    )


def _json_object(value: str | JsonValue) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(value)) if isinstance(value, str) else value
    assert isinstance(payload, dict)
    return payload


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _json_string(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
