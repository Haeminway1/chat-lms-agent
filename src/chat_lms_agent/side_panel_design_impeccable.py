from __future__ import annotations

import json
import subprocess
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

_IMPECCABLE_VERSION: Final = "2.3.2"
_IMPECCABLE_TIMEOUT_SECONDS: Final = 15.0
_INSTALL_HINT: Final = "npx impeccable skills install"


def impeccable_advisory(artifact_path: Path) -> dict[str, JsonValue]:
    command = (
        "npx",
        "--no-install",
        f"impeccable@{_IMPECCABLE_VERSION}",
        "detect",
        str(artifact_path),
        "--fast",
        "--json",
    )
    try:
        result = subprocess.run(  # noqa: S603 - fixed local npx command tuple, no shell.
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=_IMPECCABLE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return _skipped()
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "reason": "impeccable timed out"}
    if result.returncode not in {0, 2}:
        return _skipped()
    try:
        payload = cast("JsonValue", json.loads(result.stdout))
    except JSONDecodeError:
        return {"status": "ERROR", "reason": "impeccable returned invalid JSON"}
    return _advisory_payload(payload)


def _advisory_payload(payload: JsonValue) -> dict[str, JsonValue]:
    if isinstance(payload, list):
        return {"status": "PASS" if not payload else "FINDINGS", "findings": payload}
    if not isinstance(payload, dict):
        return {"status": "ERROR", "reason": "impeccable returned non-object JSON"}
    findings = payload.get("findings")
    if "findings" not in payload:
        payload["findings"] = []
    if "status" not in payload:
        payload["status"] = "PASS" if findings in (None, []) else "FINDINGS"
    return payload


def _skipped() -> dict[str, JsonValue]:
    return {
        "status": "SKIPPED",
        "reason": "impeccable not installed",
        "install_hint": _INSTALL_HINT,
    }
