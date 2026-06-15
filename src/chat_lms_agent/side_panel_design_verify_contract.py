from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal

from chat_lms_agent.side_panel import VIEWS, side_panel_view_draft

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

VerifyMode = Literal["panel", "fullscreen", "all"]

VERIFY_EVIDENCE_SCHEMA_VERSION: Final = "side-panel-design-verify-evidence-v1"
DISPLAY_SPEC_VERSION: Final = "display-spec-v1"
_SIDE_PANEL_MODES_META_NAME: Final = (
    r"<meta\b(?=[^>]*\bname\s*=\s*['\"]side-panel-modes['\"])[^>]*"
)
_SIDE_PANEL_MODES_META_CONTENT: Final = (
    r"\bcontent\s*=\s*['\"](?P<content>[^'\"]*)['\"][^>]*>"
)
_SIDE_PANEL_MODES_META_TEXT: Final = (
    f"{_SIDE_PANEL_MODES_META_NAME}{_SIDE_PANEL_MODES_META_CONTENT}"
)
_SIDE_PANEL_MODES_META: Final[re.Pattern[str]] = re.compile(
    _SIDE_PANEL_MODES_META_TEXT,
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class VerifyFixtures:
    fixture_a: dict[str, JsonValue]
    fixture_b: dict[str, JsonValue]
    markers_a: tuple[str, ...]
    markers_b: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerifyEvidenceParts:
    artifact_path: Path
    view: str
    mode: VerifyMode
    checked_modes: tuple[str, ...]
    lint_payload: dict[str, JsonValue]
    checks: list[JsonValue]


def build_verify_fixtures(view: str) -> VerifyFixtures:
    if view not in VIEWS:
        return VerifyFixtures({}, {}, (), ())
    markers_a = _markers_for_variant(view, "A")
    markers_b = _markers_for_variant(view, "B")
    return VerifyFixtures(
        fixture_a=_fixture_payload(view, "A", markers_a),
        fixture_b=_fixture_payload(view, "B", markers_b),
        markers_a=markers_a,
        markers_b=markers_b,
    )


def build_verify_evidence(parts: VerifyEvidenceParts) -> dict[str, JsonValue]:
    verify_status = "PASS" if _all_checks_pass(parts.checks) else "FAIL"
    status = (
        "PASS"
        if parts.lint_payload.get("status") == "PASS" and verify_status == "PASS"
        else "ERROR"
    )
    payload: dict[str, JsonValue] = {
        "schema_version": VERIFY_EVIDENCE_SCHEMA_VERSION,
        "spec_version": DISPLAY_SPEC_VERSION,
        "status": status,
        "artifact": str(parts.artifact_path),
        "artifact_sha256": artifact_sha256(parts.artifact_path),
        "view": parts.view,
        "mode": parts.mode,
        "checked_modes": [*parts.checked_modes],
        "timestamp_utc": datetime.now(tz=UTC).isoformat(),
        "lint": parts.lint_payload,
        "verify": {"status": verify_status},
        "checks": parts.checks,
    }
    if status != "PASS":
        payload["error_code"] = "DESIGN_VERIFY_FAILED"
    return payload


def artifact_sha256(artifact_path: Path) -> str:
    return hashlib.sha256(artifact_path.read_bytes()).hexdigest()


def checked_modes_from_artifact(html: str, mode: VerifyMode) -> tuple[str, ...]:
    match mode:
        case "panel":
            return ("panel",)
        case "fullscreen":
            return ("fullscreen",)
        case "all":
            declared = declared_modes_from_artifact(html)
            if "fullscreen" in declared:
                return ("panel", "fullscreen")
            return ("panel",)


def declared_modes_from_artifact(html: str) -> tuple[str, ...]:
    match = _SIDE_PANEL_MODES_META.search(html)
    if match is None:
        return ()
    return tuple(part for part in match.group("content").split() if part)


def _all_checks_pass(checks: list[JsonValue]) -> bool:
    if not checks:
        return False
    for check in checks:
        if not isinstance(check, dict) or check.get("status") != "PASS":
            return False
    return True


def _markers_for_variant(view: str, variant: str) -> tuple[str, ...]:
    sections = _required_sections(view)
    markers = [
        f"D4_FIXTURE_{variant}_{view.upper()}_TITLE",
        f"D4_FIXTURE_{variant}_{view.upper()}_WARNING",
        f"D4_FIXTURE_{variant}_{view.upper()}_SOURCE_COMMAND",
    ]
    markers.extend(f"D4_FIXTURE_{variant}_{view.upper()}_{section.upper()}" for section in sections)
    return tuple(markers)


def _fixture_payload(
    view: str,
    variant: str,
    markers: tuple[str, ...],
) -> dict[str, JsonValue]:
    section_markers = {
        section: f"D4_FIXTURE_{variant}_{view.upper()}_{section.upper()}"
        for section in _required_sections(view)
    }
    return {
        "synthetic": True,
        "schema_version": "side-panel-verify-fixture-v1",
        "view_id": view,
        "title": f"D4_FIXTURE_{variant}_{view.upper()}_TITLE",
        "subtitle": f"D4 fixture {variant}",
        "entity_ref": f"learner:가상학생-{variant}",
        "generated_at": "2026-06-12T00:00:00+00:00",
        "privacy_level": "learner",
        "warnings": [
            {
                "level": "warning",
                "message": f"D4_FIXTURE_{variant}_{view.upper()}_WARNING",
            },
        ],
        "sections": [
            _section_payload(section, marker) for section, marker in section_markers.items()
        ],
        "source_commands": [
            {
                "query_name": "synthetic-fixture",
                "command": f"D4_FIXTURE_{variant}_{view.upper()}_SOURCE_COMMAND",
            },
        ],
        "design_tokens": {
            "theme": "system",
            "accent": "#3182F6",
            "density": "comfy",
            "round": "soft",
            "fontSize": 15,
        },
        "marker_digest": hashlib.sha256(json.dumps(markers).encode("utf-8")).hexdigest(),
    }


def _section_payload(section: str, marker: str) -> dict[str, JsonValue]:
    return {
        "type": section,
        "text": marker,
        "items": [
            {"label": marker, "value": f"{marker}_VALUE", "status": marker},
        ],
        "metrics": [
            {"label": marker, "value": "1"},
        ],
        "events": [
            {"label": marker, "description": marker},
        ],
        "actions": [
            {"label": marker, "command": marker},
        ],
    }


def _required_sections(view: str) -> tuple[str, ...]:
    draft = side_panel_view_draft(view)
    raw_sections = draft.get("required_sections")
    if not isinstance(raw_sections, list):
        return ()
    return tuple(section for section in raw_sections if isinstance(section, str))
