from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

_HTML_FENCE: Final[re.Pattern[str]] = re.compile(
    r"```(?:html)?\s*(?P<html>.*?)```",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class GenerationContext:
    view: str
    modes: tuple[str, ...]
    design_system_id: str
    design_markdown: str
    display_spec_json: str
    view_payload_schema_json: str
    synthetic_fixture_json: str
    brief: str | None
    hard_constraints: tuple[str, ...]
    prompt: str
    refinement_findings_json: str | None = None


@dataclass(frozen=True, slots=True)
class EngineSuccess:
    artifact_html: str
    engine_notes: str


@dataclass(frozen=True, slots=True)
class EngineBlocked:
    error_code: str
    message: str
    hint: str | None = None
    install_hint: str | None = None


type EngineRunResult = EngineSuccess | EngineBlocked


class DesignEngine(Protocol):
    engine_id: str

    def generate(self, context: GenerationContext) -> EngineRunResult:
        """Return one generated artifact or a typed local-blocked result."""
        ...


def with_refinement_findings(
    context: GenerationContext,
    findings: list[JsonValue],
) -> GenerationContext:
    findings_json = json.dumps(findings, ensure_ascii=False, indent=2, sort_keys=True)
    prompt = (
        f"{context.prompt}\n\n"
        "Refinement instruction: fix these detector findings, change nothing else.\n"
        f"{findings_json}\n"
    )
    return replace(context, prompt=prompt, refinement_findings_json=findings_json)


def extract_html_artifact(text: str) -> str | None:
    for match in _HTML_FENCE.finditer(text):
        candidate = match.group("html").strip()
        if _looks_like_complete_html(candidate):
            return candidate + "\n"
    start = text.lower().find("<html")
    end = text.lower().rfind("</html>")
    if start == -1 or end == -1 or end < start:
        return None
    doctype = text.lower().rfind("<!doctype", 0, start)
    if doctype != -1:
        start = doctype
    return text[start : end + len("</html>")].strip() + "\n"


def _looks_like_complete_html(text: str) -> bool:
    lowered = text.lower()
    return "<html" in lowered and "</html>" in lowered
