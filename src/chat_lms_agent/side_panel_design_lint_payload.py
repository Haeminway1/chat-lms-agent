from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

LintMode = Literal["panel", "fullscreen", "all"]


def error_payload(
    error_code: str,
    errors: list[str],
    mode: LintMode,
    checked_modes: tuple[str, ...],
    advisory: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return {
        "status": "ERROR",
        "error_code": error_code,
        "mode": mode,
        "checked_modes": [*checked_modes],
        "errors": [*errors],
        "advisory": advisory,
    }
