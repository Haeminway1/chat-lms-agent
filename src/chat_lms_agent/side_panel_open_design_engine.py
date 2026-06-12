from __future__ import annotations

import json
import os
import shutil
import subprocess
from http.client import HTTPConnection, HTTPException
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast
from urllib import parse

from chat_lms_agent.side_panel_design_engine_contract import (
    EngineBlocked,
    EngineRunResult,
    EngineSuccess,
    GenerationContext,
    extract_html_artifact,
)

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

_OPEN_DESIGN_TIMEOUT_SECONDS: Final = 120.0
_OPEN_DESIGN_IDENTITY_TIMEOUT_SECONDS: Final = 5.0
_OPEN_DESIGN_INSTALL_HINT: Final = (
    "Install nexu-io/open-design locally at the pinned SHA recorded in "
    "docs/oss-reference-registry.md, then start the 127.0.0.1 daemon or install od."
)
_OPEN_DESIGN_IDENTITY_ARGS: Final = (("--version",), ("version",), ("version", "--json"))
_OPEN_DESIGN_MARKERS: Final = ("open-design", "nexu-io/open-design")


class OpenDesignEngine:
    engine_id: str = "open-design"

    def generate(self, context: GenerationContext) -> EngineRunResult:
        """Run a positively identified local open-design adapter."""
        od = _open_design_cli_path()
        if od is not None:
            return _run_open_design_cli(od, context)
        daemon = os.environ.get("CHAT_LMS_OPEN_DESIGN_DAEMON")
        if daemon:
            return _run_open_design_daemon(daemon, context)
        return _open_design_missing()


def _open_design_cli_path() -> str | None:
    od = shutil.which("od")
    if od is None:
        return None
    return od if _is_open_design_cli(od) else None


def _is_open_design_cli(od: str) -> bool:
    for args in _OPEN_DESIGN_IDENTITY_ARGS:
        try:
            result = subprocess.run(  # noqa: S603 - resolved local executable, no shell.
                (od, *args),
                capture_output=True,
                check=False,
                text=True,
                timeout=_OPEN_DESIGN_IDENTITY_TIMEOUT_SECONDS,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        identity = f"{result.stdout}\n{result.stderr}".lower()
        if any(marker in identity for marker in _OPEN_DESIGN_MARKERS):
            return True
    return False


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


def _trim_text(text: str) -> str:
    return text.strip().replace("\r", " ")[:500]
