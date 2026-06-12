from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from http.client import HTTPConnection, HTTPException
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast
from urllib import parse

from chat_lms_agent.hosts import (
    DESIGN_GENERATION_DEFAULT_AUTH_HINT,
    DESIGN_GENERATION_DEFAULT_CLI,
    DESIGN_GENERATION_DEFAULT_EXEC_ARGS,
    DESIGN_GENERATION_DEFAULT_FAILED_CODE,
    DESIGN_GENERATION_DEFAULT_FAILED_MESSAGE,
    DESIGN_GENERATION_DEFAULT_MISSING_ARTIFACT_MESSAGE,
    DESIGN_GENERATION_DEFAULT_NOT_FOUND_CODE,
    DESIGN_GENERATION_DEFAULT_NOT_FOUND_MESSAGE,
    DESIGN_GENERATION_DEFAULT_SUCCESS_NOTE,
    DESIGN_GENERATION_DEFAULT_TIMEOUT_CODE,
    DESIGN_GENERATION_DEFAULT_TIMEOUT_MESSAGE,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chat_lms_agent.state import JsonValue

_DEFAULT_ENGINE_TIMEOUT_SECONDS: Final = 600.0
_OPEN_DESIGN_TIMEOUT_SECONDS: Final = 120.0
_OPEN_DESIGN_INSTALL_HINT: Final = (
    "Install nexu-io/open-design locally at the pinned SHA recorded in "
    "docs/oss-reference-registry.md, then start the 127.0.0.1 daemon or install od."
)
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


class CodexDesignEngine:
    engine_id: str = DESIGN_GENERATION_DEFAULT_CLI

    def generate(self, context: GenerationContext) -> EngineRunResult:
        """Run the default local engine CLI with the composed context."""
        cli_path = shutil.which(DESIGN_GENERATION_DEFAULT_CLI)
        if cli_path is None:
            return EngineBlocked(
                error_code=DESIGN_GENERATION_DEFAULT_NOT_FOUND_CODE,
                message=DESIGN_GENERATION_DEFAULT_NOT_FOUND_MESSAGE,
                hint=DESIGN_GENERATION_DEFAULT_AUTH_HINT,
            )
        try:
            result = subprocess.run(  # noqa: S603 - resolved local executable, no shell.
                (cli_path, *DESIGN_GENERATION_DEFAULT_EXEC_ARGS),
                input=context.prompt,
                capture_output=True,
                check=False,
                text=True,
                timeout=_DEFAULT_ENGINE_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return EngineBlocked(
                error_code=DESIGN_GENERATION_DEFAULT_NOT_FOUND_CODE,
                message=DESIGN_GENERATION_DEFAULT_NOT_FOUND_MESSAGE,
                hint=DESIGN_GENERATION_DEFAULT_AUTH_HINT,
            )
        except subprocess.TimeoutExpired:
            return EngineBlocked(
                error_code=DESIGN_GENERATION_DEFAULT_TIMEOUT_CODE,
                message=DESIGN_GENERATION_DEFAULT_TIMEOUT_MESSAGE,
            )
        if result.returncode != 0:
            return EngineBlocked(
                error_code=DESIGN_GENERATION_DEFAULT_FAILED_CODE,
                message=DESIGN_GENERATION_DEFAULT_FAILED_MESSAGE,
                hint=_trim_text(result.stderr or result.stdout),
            )
        artifact = extract_html_artifact(result.stdout)
        if artifact is None:
            return EngineBlocked(
                error_code="ENGINE_ARTIFACT_NOT_FOUND",
                message=DESIGN_GENERATION_DEFAULT_MISSING_ARTIFACT_MESSAGE,
            )
        return EngineSuccess(
            artifact_html=artifact,
            engine_notes=DESIGN_GENERATION_DEFAULT_SUCCESS_NOTE,
        )


class OpenDesignEngine:
    engine_id: str = "open-design"

    def generate(self, context: GenerationContext) -> EngineRunResult:
        """Run the local `od` CLI or localhost daemon with the same brief."""
        od = shutil.which("od")
        if od is not None:
            return _run_open_design_cli(od, context)
        daemon = os.environ.get("CHAT_LMS_OPEN_DESIGN_DAEMON")
        if daemon:
            return _run_open_design_daemon(daemon, context)
        return EngineBlocked(
            error_code="OPEN_DESIGN_NOT_INSTALLED",
            message="open-design local daemon and od CLI were not found",
            install_hint=_OPEN_DESIGN_INSTALL_HINT,
        )


class EnvFixtureDesignEngine:
    engine_id: str = "fake"

    def generate(self, context: GenerationContext) -> EngineRunResult:
        """Return an HTML fixture for manual local CLI QA."""
        fixture = os.environ.get("CHAT_LMS_AGENT_TEST_DESIGN_ENGINE_ARTIFACT")
        if fixture is None:
            return EngineBlocked(
                error_code="FAKE_DESIGN_ENGINE_NOT_CONFIGURED",
                message="fake design engine requires CHAT_LMS_AGENT_TEST_DESIGN_ENGINE_ARTIFACT",
            )
        try:
            artifact = Path(fixture).read_text(encoding="utf-8")
        except OSError as error_message:
            return EngineBlocked(
                error_code="FAKE_DESIGN_ENGINE_ARTIFACT_MISSING",
                message=str(error_message),
            )
        return EngineSuccess(
            artifact_html=artifact,
            engine_notes=f"fake fixture for {context.view}",
        )


type EngineFactory = Callable[[], DesignEngine]

_ENGINE_FACTORIES: dict[str, EngineFactory] = {}


def reset_design_engines_for_tests() -> None:
    _ENGINE_FACTORIES.clear()
    _register_default_engines()


def register_design_engine_for_tests(engine: DesignEngine) -> None:
    _ENGINE_FACTORIES[engine.engine_id] = lambda: engine


def resolve_design_engine(engine_id: str) -> DesignEngine | None:
    if not _ENGINE_FACTORIES:
        _register_default_engines()
    factory = _ENGINE_FACTORIES.get(engine_id)
    if factory is None:
        return None
    return factory()


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


def _register_default_engines() -> None:
    _ENGINE_FACTORIES[DESIGN_GENERATION_DEFAULT_CLI] = CodexDesignEngine
    _ENGINE_FACTORIES["open-design"] = OpenDesignEngine
    if os.environ.get("CHAT_LMS_AGENT_TEST_DESIGN_ENGINE_ARTIFACT"):
        _ENGINE_FACTORIES["fake"] = EnvFixtureDesignEngine


def _run_open_design_cli(od: str, context: GenerationContext) -> EngineRunResult:
    try:
        result = subprocess.run(  # noqa: S603 - resolved local executable, no shell.
            (od, "generate", "--json"),
            input=context.prompt,
            capture_output=True,
            check=False,
            text=True,
            timeout=_OPEN_DESIGN_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return _open_design_missing()
    except subprocess.TimeoutExpired:
        return EngineBlocked(
            error_code="OPEN_DESIGN_TIMEOUT",
            message="open-design CLI timed out while generating the side-panel design",
        )
    if result.returncode != 0:
        return EngineBlocked(
            error_code="OPEN_DESIGN_FAILED",
            message="open-design CLI returned a non-zero exit code",
            hint=_trim_text(result.stderr or result.stdout),
        )
    artifact = _artifact_from_json_or_text(result.stdout)
    if artifact is None:
        return EngineBlocked(
            error_code="ENGINE_ARTIFACT_NOT_FOUND",
            message="open-design response did not contain a complete HTML artifact",
        )
    return EngineSuccess(artifact_html=artifact, engine_notes="od generate")


def _run_open_design_daemon(daemon: str, context: GenerationContext) -> EngineRunResult:
    if not _is_local_daemon_url(daemon):
        return EngineBlocked(
            error_code="OPEN_DESIGN_NON_LOCAL_ENDPOINT",
            message="open-design daemon URL must be localhost or 127.0.0.1",
        )
    parsed = parse.urlparse(daemon)
    body = json.dumps({"brief": context.prompt}, ensure_ascii=False).encode("utf-8")
    connection = HTTPConnection(
        parsed.hostname or "127.0.0.1",
        parsed.port or 80,
        timeout=_OPEN_DESIGN_TIMEOUT_SECONDS,
    )
    try:
        connection.request(
            "POST",
            _daemon_generate_path(parsed.path),
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        text = response.read().decode("utf-8")
    except (HTTPException, OSError, TimeoutError):
        return _open_design_missing()
    finally:
        connection.close()
    artifact = _artifact_from_json_or_text(text)
    if artifact is None:
        return EngineBlocked(
            error_code="ENGINE_ARTIFACT_NOT_FOUND",
            message="open-design daemon response did not contain a complete HTML artifact",
        )
    return EngineSuccess(artifact_html=artifact, engine_notes="open-design daemon")


def _artifact_from_json_or_text(text: str) -> str | None:
    try:
        payload = cast("JsonValue", json.loads(text))
    except JSONDecodeError:
        return extract_html_artifact(text)
    match payload:
        case {"artifact_html": str(artifact)} | {"html": str(artifact)}:
            return artifact if artifact.endswith("\n") else artifact + "\n"
        case {"artifact": str(artifact)}:
            return extract_html_artifact(artifact)
        case _:
            return extract_html_artifact(text)


def _open_design_missing() -> EngineBlocked:
    return EngineBlocked(
        error_code="OPEN_DESIGN_NOT_INSTALLED",
        message="open-design local daemon and od CLI were not found",
        install_hint=_OPEN_DESIGN_INSTALL_HINT,
    )


def _is_local_daemon_url(raw_url: str) -> bool:
    parsed = parse.urlparse(raw_url)
    match parsed.hostname:
        case "127.0.0.1" | "localhost" | "::1":
            return parsed.scheme == "http"
        case None:
            return False
        case _:
            return False


def _daemon_generate_path(path: str) -> str:
    base = path.rstrip("/")
    if not base:
        return "/api/generate"
    return base + "/api/generate"


def _looks_like_complete_html(text: str) -> bool:
    lowered = text.lower()
    return "<html" in lowered and "</html>" in lowered


def _trim_text(text: str) -> str:
    return text.strip().replace("\r", " ")[:500]
