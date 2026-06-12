from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final

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
from chat_lms_agent.side_panel_design_engine_contract import (
    DesignEngine,
    EngineBlocked,
    EngineRunResult,
    EngineSuccess,
    GenerationContext,
    extract_html_artifact,
)
from chat_lms_agent.side_panel_open_design_engine import OpenDesignEngine

if TYPE_CHECKING:
    from collections.abc import Callable

_DEFAULT_ENGINE_TIMEOUT_SECONDS: Final = 600.0


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


def _register_default_engines() -> None:
    _ENGINE_FACTORIES[DESIGN_GENERATION_DEFAULT_CLI] = CodexDesignEngine
    _ENGINE_FACTORIES["open-design"] = OpenDesignEngine
    if os.environ.get("CHAT_LMS_AGENT_TEST_DESIGN_ENGINE_ARTIFACT"):
        _ENGINE_FACTORIES["fake"] = EnvFixtureDesignEngine


def _trim_text(text: str) -> str:
    return text.strip().replace("\r", " ")[:500]
