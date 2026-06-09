from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.side_panel import SECTION_TYPES, TOKEN_AXES, VIEWS

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

_HEXADECIMAL: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ITEM_LIST_SECTION_TYPES: Final[frozenset[str]] = frozenset(
    {"metric_grid", "entity_list", "timeline", "task_list"},
)
_PRIVACY_LEVELS: Final[tuple[str, ...]] = (
    "workspace",
    "profile",
    "class",
    "learner",
    "tool",
    "schema",
    "side_panel",
)
_FONT_SIZE_MIN: Final[int] = 13
_FONT_SIZE_MAX: Final[int] = 18


def side_panel_payload_validate(payload_path: Path) -> tuple[int, dict[str, JsonValue]]:
    try:
        payload = cast("JsonValue", json.loads(payload_path.read_text(encoding="utf-8-sig")))
    except (OSError, JSONDecodeError) as error:
        return 1, _error_payload("INVALID_JSON", [str(error)])
    if not isinstance(payload, dict):
        return 1, {
            "status": "ERROR",
            "error_code": "INVALID_PAYLOAD",
            "errors": _json_strings(["top-level payload must be an object"]),
        }

    errors: list[str] = []
    _require_top_level_fields(payload, errors)
    _validate_source_commands(payload, errors)
    _validate_sections(payload.get("sections"), errors)
    _validate_source_commands_objects(payload.get("source_commands"), errors)
    _validate_design_tokens(payload.get("design_tokens"), errors)

    if errors:
        return 2, _error_payload("INVALID_PAYLOAD", errors)
    return 0, {"status": "PASS", "warnings": _json_strings([])}


def _require_top_level_fields(payload: dict[str, JsonValue], errors: list[str]) -> None:
    for key in (
        "schema_version",
        "view_id",
        "title",
        "subtitle",
        "entity_ref",
        "generated_at",
        "privacy_level",
        "sections",
    ):
        if key not in payload:
            errors.append(f"missing required key: {key}")
            continue
        if key == "view_id" and payload[key] not in VIEWS:
            errors.append(f"unsupported view_id: {payload[key]!r}")
    if payload.get("privacy_level") not in _PRIVACY_LEVELS:
        allowed = ", ".join(_PRIVACY_LEVELS)
        errors.append(f"privacy_level must be one of {allowed}")


def _validate_source_commands(payload: dict[str, JsonValue], errors: list[str]) -> None:
    if payload.get("synthetic") is True:
        return
    source_commands = payload.get("source_commands")
    if source_commands is None:
        errors.append("source_commands is required for production payloads")
        return
    if not isinstance(source_commands, list):
        errors.append("source_commands must be a list")


def _validate_source_commands_objects(raw_commands: JsonValue | None, errors: list[str]) -> None:
    if not isinstance(raw_commands, list):
        return
    for index, item in enumerate(raw_commands):
        if not isinstance(item, dict):
            errors.append(f"source_commands[{index}] must be an object")
            continue
        command = item.get("command")
        query_name = item.get("query_name")
        if not isinstance(command, str) or not command:
            errors.append(f"source_commands[{index}] missing command")
        if not isinstance(query_name, str) or not query_name:
            errors.append(f"source_commands[{index}] missing query_name")


def _validate_sections(raw_sections: JsonValue | None, errors: list[str]) -> None:
    if not isinstance(raw_sections, list):
        errors.append("sections must be a list")
        return
    for index, section in enumerate(raw_sections):
        if not isinstance(section, dict):
            errors.append(f"sections[{index}] must be an object")
            continue
        section_type = section.get("type")
        if not isinstance(section_type, str):
            errors.append(f"sections[{index}] type must be string")
            continue
        if section_type not in SECTION_TYPES:
            errors.append(f"unknown section type: {section_type!r}")
            continue
        _validate_known_section(section, section_type, index, errors)


def _validate_known_section(
    section: dict[str, JsonValue],
    section_type: str,
    index: int,
    errors: list[str],
) -> None:
    if section_type == "summary":
        if not isinstance(section.get("text"), str):
            errors.append(f"sections[{index}] summary requires text")
        return
    if section_type in _ITEM_LIST_SECTION_TYPES:
        if not isinstance(section.get("items"), list):
            errors.append(f"sections[{index}] {section_type} requires items list")
        return
    if section_type == "action_group":
        _validate_action_group(section, index, errors)


def _validate_action_group(
    section: dict[str, JsonValue],
    index: int,
    errors: list[str],
) -> None:
    actions = section.get("actions")
    if not isinstance(actions, list):
        errors.append(f"sections[{index}] action_group requires actions list")
        return
    for action_index, action in enumerate(actions):
        if not isinstance(action, dict):
            errors.append(f"sections[{index}].actions[{action_index}] must be an object")
            continue
        _validate_action(action, index, action_index, errors)


def _validate_action(
    action: dict[str, JsonValue],
    section_index: int,
    action_index: int,
    errors: list[str],
) -> None:
    prefix = f"sections[{section_index}].actions[{action_index}]"
    if not isinstance(action.get("label"), str) or not action.get("label"):
        errors.append(f"{prefix} missing label")
    if not isinstance(action.get("intent"), str) or not action.get("intent"):
        errors.append(f"{prefix} missing intent")
    if not isinstance(action.get("requires_approval"), bool):
        errors.append(f"{prefix} requires_approval must be bool")
    if not isinstance(action.get("dry_run_default"), bool):
        errors.append(f"{prefix} dry_run_default must be bool")


def _validate_design_tokens(raw_tokens: JsonValue | None, errors: list[str]) -> None:
    if raw_tokens is None:
        return
    if not isinstance(raw_tokens, dict):
        errors.append("design_tokens must be an object")
        return
    if "accent" in raw_tokens:
        _validate_accent(raw_tokens.get("accent"), errors)
    if raw_tokens.get("theme") not in (*_allowed_values("theme"), None):
        errors.append("design_tokens.theme must be one of light, dark, system")
    if raw_tokens.get("density") not in (*_allowed_values("density"), None):
        errors.append("design_tokens.density must be one of compact, comfy, roomy")
    if raw_tokens.get("round") not in (*_allowed_values("round"), None):
        errors.append("design_tokens.round must be one of sharp, soft, round")
    font_size = raw_tokens.get("fontSize")
    if font_size is not None and not (
        isinstance(font_size, int) and _FONT_SIZE_MIN <= font_size <= _FONT_SIZE_MAX
    ):
        errors.append("design_tokens.fontSize must be an integer from 13 to 18")


def _validate_accent(value: JsonValue | None, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append("design_tokens.accent must be a string")
        return
    if not _HEXADECIMAL.match(value):
        errors.append("design_tokens.accent must be hex color like #RRGGBB")


def _allowed_values(axis: str) -> tuple[str, ...]:
    axis_config = TOKEN_AXES.get(axis)
    if not isinstance(axis_config, dict):
        return ()
    values = axis_config.get("allowed")
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str))


def _error_payload(error_code: str, errors: list[str]) -> dict[str, JsonValue]:
    return {
        "status": "ERROR",
        "error_code": error_code,
        "errors": _json_strings(errors),
    }


def _json_strings(values: list[str]) -> list[JsonValue]:
    return [*values]
