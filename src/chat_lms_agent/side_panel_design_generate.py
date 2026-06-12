from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from chat_lms_agent.hosts import DESIGN_GENERATION_DEFAULT_ENGINE_ID
from chat_lms_agent.side_panel import (
    BLOCK_CATALOG,
    SECTION_TYPES,
    TOKEN_AXES,
    VIEWS,
    side_panel_view_draft,
)
from chat_lms_agent.side_panel_blocks import BLOCK_DRAFTS_DIR, scaffold_block
from chat_lms_agent.side_panel_design_engine import (
    DesignEngine,
    EngineBlocked,
    EngineRunResult,
    EngineSuccess,
    GenerationContext,
    register_design_engine_for_tests,
    reset_design_engines_for_tests,
    resolve_design_engine,
    with_refinement_findings,
)
from chat_lms_agent.side_panel_design_lint import side_panel_design_lint
from chat_lms_agent.side_panel_design_systems import DesignSystem, load_design_systems
from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

type GenerateMode = Literal["panel", "fullscreen"]

__all__ = (
    "DesignGenerateRequest",
    "EngineSuccess",
    "GenerationContext",
    "generate_side_panel_design",
    "parse_generate_modes",
    "register_design_engine_for_tests",
    "reset_design_engines_for_tests",
)

_DEFAULT_DESIGN_SYSTEM: Final = "toss-style"
_DEFAULT_ENGINE: Final = DESIGN_GENERATION_DEFAULT_ENGINE_ID
_DISPLAY_SPEC_PATH: Final = Path("assets/side-panel/display-spec-v1.json")
_FINAL_ARTIFACT: Final = "artifact.html"
_EVIDENCE_FILE: Final = "evidence.json"


@dataclass(frozen=True, slots=True)
class DesignGenerateRequest:
    view: str
    modes: tuple[GenerateMode, ...]
    design_system_id: str | None
    brief: str | None
    engine_id: str | None


@dataclass(frozen=True, slots=True)
class _PromptParts:
    engine_id: str
    request: DesignGenerateRequest
    design_markdown: str
    display_spec_json: str
    view_payload_schema_json: str
    synthetic_fixture_json: str
    constraints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SuccessPayloadParts:
    request: DesignGenerateRequest
    engine_id: str
    block_id: str
    final_path: Path
    final_lint: dict[str, JsonValue]
    evidence: list[JsonValue]
    refinement_iterations: int
    scaffold_payload: dict[str, JsonValue]


def generate_side_panel_design(
    profile: ProfileState,
    request: DesignGenerateRequest,
) -> tuple[int, dict[str, JsonValue]]:
    engine_id = request.engine_id or _DEFAULT_ENGINE
    engine = resolve_design_engine(engine_id)
    if engine is None:
        return 2, {
            "status": "ERROR",
            "error_code": "UNKNOWN_DESIGN_ENGINE",
            "engine": engine_id,
        }
    context_result = _compose_context(profile, request, engine_id)
    match context_result:
        case dict():
            return 2, context_result
        case GenerationContext():
            return _run_generation(profile, request, engine, context_result)


def parse_generate_modes(raw_modes: str | None) -> tuple[GenerateMode, ...] | None:
    if raw_modes is None or raw_modes.strip() == "":
        return ("panel", "fullscreen")
    parts = tuple(part.strip() for part in raw_modes.split(",") if part.strip())
    match parts:
        case ("panel",):
            return ("panel",)
        case ("panel", "fullscreen"):
            return ("panel", "fullscreen")
        case _:
            return None


def _run_generation(
    profile: ProfileState,
    request: DesignGenerateRequest,
    engine: DesignEngine,
    context: GenerationContext,
) -> tuple[int, dict[str, JsonValue]]:
    first = engine.generate(context)
    blocked = _blocked_payload(engine.engine_id, first)
    if blocked is not None:
        return 5, blocked
    first_success = _engine_success(first)
    block_id = _draft_block_id(context, first_success.artifact_html, engine.engine_id)
    scaffold_code, scaffold_payload = _scaffold_generated_draft(profile, request, block_id)
    if scaffold_code != 0:
        return scaffold_code, scaffold_payload
    quarantine = _quarantine_dir(profile, block_id)
    evidence: list[JsonValue] = []
    round_one = _write_and_check_round(quarantine, 1, first_success.artifact_html)
    evidence.append(round_one)
    final_artifact = first_success.artifact_html
    final_lint = _json_object(round_one["lint"])
    refinement_iterations = 0
    findings = _json_list(round_one["findings"])
    if findings:
        refined = engine.generate(with_refinement_findings(context, findings))
        blocked = _blocked_payload(engine.engine_id, refined)
        if blocked is not None:
            _write_evidence(quarantine, evidence)
            return 5, blocked
        refined_success = _engine_success(refined)
        round_two = _write_and_check_round(quarantine, 2, refined_success.artifact_html)
        evidence.append(round_two)
        final_artifact = refined_success.artifact_html
        final_lint = _json_object(round_two["lint"])
        refinement_iterations = 1
    final_path = quarantine / _FINAL_ARTIFACT
    _ = final_path.write_text(final_artifact, encoding="utf-8")
    _write_evidence(quarantine, evidence)
    return 0, _success_payload(
        _SuccessPayloadParts(
            request=request,
            engine_id=engine.engine_id,
            block_id=block_id,
            final_path=final_path,
            final_lint=final_lint,
            evidence=evidence,
            refinement_iterations=refinement_iterations,
            scaffold_payload=scaffold_payload,
        ),
    )


def _compose_context(
    profile: ProfileState,
    request: DesignGenerateRequest,
    engine_id: str,
) -> GenerationContext | dict[str, JsonValue]:
    if request.view not in VIEWS:
        return {"status": "ERROR", "error_code": "UNKNOWN_SIDE_PANEL_VIEW", "view": request.view}
    selected = request.design_system_id or _DEFAULT_DESIGN_SYSTEM
    design_system, warnings = _resolve_design_system(profile, selected)
    if design_system is None:
        return {
            "status": "ERROR",
            "error_code": "UNKNOWN_DESIGN_SYSTEM",
            "design_system": selected,
            "warnings": warnings,
        }
    try:
        design_markdown = design_system.design_path.read_text(encoding="utf-8-sig")
        display_spec_json = (profile.repo_root / _DISPLAY_SPEC_PATH).read_text(encoding="utf-8")
    except OSError as error:
        return {
            "status": "ERROR",
            "error_code": "DESIGN_CONTEXT_READ_FAILED",
            "message": str(error),
        }
    view_payload_schema_json = _view_payload_schema_json(request.view)
    synthetic_fixture_json = _synthetic_fixture_json(request.view)
    constraints = _hard_constraints(request.modes)
    prompt = _compose_prompt(
        _PromptParts(
            engine_id=engine_id,
            request=request,
            design_markdown=design_markdown,
            display_spec_json=display_spec_json,
            view_payload_schema_json=view_payload_schema_json,
            synthetic_fixture_json=synthetic_fixture_json,
            constraints=constraints,
        ),
    )
    return GenerationContext(
        view=request.view,
        modes=request.modes,
        design_system_id=selected,
        design_markdown=design_markdown,
        display_spec_json=display_spec_json,
        view_payload_schema_json=view_payload_schema_json,
        synthetic_fixture_json=synthetic_fixture_json,
        brief=request.brief,
        hard_constraints=constraints,
        prompt=prompt,
    )


def _resolve_design_system(
    profile: ProfileState,
    system_id: str,
) -> tuple[DesignSystem | None, list[JsonValue]]:
    systems, warnings = load_design_systems(profile.repo_root, profile)
    warning_values: list[JsonValue] = [*warnings]
    for system in systems:
        if system.system_id == system_id:
            return system, warning_values
    return None, warning_values


def _compose_prompt(parts: _PromptParts) -> str:
    sections = [
        "Generate one side-panel HTML artifact.",
        f"Engine: {parts.engine_id}",
        f"View: {parts.request.view}",
        f"Modes: {', '.join(parts.request.modes)}",
        "Teacher brief:\n" + (parts.request.brief or "(none)"),
        "Resolved DESIGN.md content:\n" + parts.design_markdown,
        "Display spec JSON:\n" + parts.display_spec_json,
        "View payload JSON schema:\n" + parts.view_payload_schema_json,
        "Synthetic fixture payload:\n" + parts.synthetic_fixture_json,
        "Hard constraints:\n" + "\n".join(f"- {constraint}" for constraint in parts.constraints),
        "Return only a single complete HTML file, preferably fenced as ```html.",
    ]
    return "\n\n".join(sections) + "\n"


def _hard_constraints(modes: tuple[GenerateMode, ...]) -> tuple[str, ...]:
    return (
        "single offline HTML file with no build step and no external http(s) assets",
        "fetch from relative /api/ endpoints only; never hardcode learner-looking data",
        "registered side-panel blocks only: " + ", ".join(BLOCK_CATALOG),
        'declare meta name="side-panel-modes" with content="' + " ".join(modes) + '"',
        "implement light and dark themes through CSS custom properties",
        "support panel mode without horizontal scroll; support fullscreen when requested",
    )


def _view_payload_schema_json(view: str) -> str:
    draft = side_panel_view_draft(view)
    schema: dict[str, JsonValue] = {
        "schema_version": "side-panel-view-payload-schema-v1",
        "view_id": view,
        "required_top_level": [
            "schema_version",
            "view_id",
            "title",
            "sections",
            "source_commands",
            "design_tokens",
        ],
        "section_types": [*SECTION_TYPES],
        "required_sections": _json_list(draft.get("required_sections")),
        "token_axes": TOKEN_AXES,
    }
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)


def _synthetic_fixture_json(view: str) -> str:
    draft = side_panel_view_draft(view)
    required_sections = _json_list(draft.get("required_sections"))
    sections: list[JsonValue] = [
        {
            "type": section,
            "marker": _fixture_marker(view, _json_string(section)),
            "text": f"가상학생 {_json_string(section)} synthetic fixture",
        }
        for section in required_sections
    ]
    fixture: dict[str, JsonValue] = {
        "synthetic": True,
        "schema_version": "side-panel-fixture-v1",
        "view_id": view,
        "title": "가상학생 side-panel fixture",
        "sections": sections,
        "source_commands": [{"query_name": "synthetic", "command": "synthetic fixture"}],
        "design_tokens": {"theme": "system", "accent": "#3182F6", "fontSize": 15},
    }
    return json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True)


def _scaffold_generated_draft(
    profile: ProfileState,
    request: DesignGenerateRequest,
    block_id: str,
) -> tuple[int, dict[str, JsonValue]]:
    proposal = _block_proposal(request, block_id)
    with tempfile.TemporaryDirectory(prefix="chat-lms-side-panel-draft-") as temp_dir:
        proposal_path = Path(temp_dir) / "proposal.json"
        _ = proposal_path.write_text(
            json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return scaffold_block(profile, proposal_path)


def _block_proposal(request: DesignGenerateRequest, block_id: str) -> dict[str, JsonValue]:
    return {
        "id": block_id,
        "label": f"Generated {request.view} design draft",
        "summary": f"Generated side-panel design draft for {request.view}.",
        "render_contract": {
            "view": request.view,
            "modes": [*request.modes],
            "artifact": _FINAL_ARTIFACT,
            "required_blocks": [*BLOCK_CATALOG],
            "api_prefix": "/api/",
        },
        "privacy_level": "side_panel",
        "action_safety": {"requires_approval": True, "dry_run_default": True},
        "test_contract": {
            "lint": "side-panel design lint --artifact <draft>/artifact.html --mode all --json",
            "promotion": "draft only; promotion requires later evidence and teacher approval",
        },
        "reuse_review": {
            "checked_existing": ["side-panel block list", "side-panel design systems list"],
            "custom_build_justification": "teacher-requested generated visual draft",
        },
    }


def _write_and_check_round(
    quarantine: Path,
    round_number: int,
    artifact_html: str,
) -> dict[str, JsonValue]:
    artifact_path = quarantine / f"artifact-round-{round_number}.html"
    _ = artifact_path.write_text(artifact_html, encoding="utf-8")
    lint_code, lint_payload = side_panel_design_lint(artifact_path, "all")
    findings = _findings_from_lint(lint_code, lint_payload)
    return {
        "round": round_number,
        "artifact_path": str(artifact_path),
        "artifact_sha256": _sha256_text(artifact_html),
        "lint_exit_code": lint_code,
        "lint": lint_payload,
        "findings": findings,
    }


def _success_payload(parts: _SuccessPayloadParts) -> dict[str, JsonValue]:
    return {
        "status": "PASS",
        "view": parts.request.view,
        "modes": [*parts.request.modes],
        "engine": parts.engine_id,
        "design_system": parts.request.design_system_id or _DEFAULT_DESIGN_SYSTEM,
        "draft": {
            "block_id": parts.block_id,
            "lifecycle_state": "draft",
            "artifact_path": str(parts.final_path),
            "quarantine": parts.scaffold_payload.get("quarantine", ""),
            "installed": False,
        },
        "preview_path": str(parts.final_path),
        "verdicts": {"lint": parts.final_lint},
        "refinement": {"iterations": parts.refinement_iterations, "max_iterations": 1},
        "evidence_trail": parts.evidence,
    }


def _blocked_payload(engine_id: str, result: EngineRunResult) -> dict[str, JsonValue] | None:
    match result:
        case EngineSuccess():
            return None
        case EngineBlocked() as blocked:
            payload: dict[str, JsonValue] = {
                "status": "BLOCKED",
                "engine": engine_id,
                "error_code": blocked.error_code,
                "message": blocked.message,
            }
            if blocked.hint is not None:
                payload["hint"] = blocked.hint
            if blocked.install_hint is not None:
                payload["install_hint"] = blocked.install_hint
            return payload


def _engine_success(result: EngineRunResult) -> EngineSuccess:
    match result:
        case EngineSuccess() as success:
            return success
        case EngineBlocked() as blocked:
            message = f"blocked result cannot be treated as success: {blocked.error_code}"
            raise RuntimeError(message)


def _findings_from_lint(
    lint_code: int,
    lint_payload: dict[str, JsonValue],
) -> list[JsonValue]:
    findings: list[JsonValue] = [
        {"source": "display-spec", "message": error}
        for error in _json_list(lint_payload.get("errors"))
    ]
    advisory = lint_payload.get("advisory")
    if isinstance(advisory, dict):
        impeccable = advisory.get("impeccable")
        if isinstance(impeccable, dict):
            findings.extend(
                {"source": "impeccable", "finding": item}
                for item in _json_list(impeccable.get("findings"))
            )
    if lint_code != 0 and not findings:
        findings.append({"source": "design-lint", "message": "lint failed without findings"})
    return findings


def _write_evidence(quarantine: Path, evidence: list[JsonValue]) -> None:
    _ = (quarantine / _EVIDENCE_FILE).write_text(
        json.dumps({"rounds": evidence}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _quarantine_dir(profile: ProfileState, block_id: str) -> Path:
    return profile.root / STATE_DIR / BLOCK_DRAFTS_DIR / block_id


def _draft_block_id(context: GenerationContext, artifact_html: str, engine_id: str) -> str:
    digest = hashlib.sha256(
        "\n".join(
            (
                context.view,
                engine_id,
                context.design_system_id,
                " ".join(context.modes),
                context.design_markdown,
                artifact_html,
            ),
        ).encode("utf-8"),
    ).hexdigest()
    return f"design-{context.view.replace('_', '-')}-{engine_id}-{digest[:12]}"


def _fixture_marker(view: str, section: str) -> str:
    return "D3_FIXTURE_" + view.upper() + "_" + section.upper()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_object(value: JsonValue | None) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    return {}


def _json_list(value: JsonValue | None) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return []


def _json_string(value: JsonValue | None) -> str:
    if isinstance(value, str):
        return value
    return ""
