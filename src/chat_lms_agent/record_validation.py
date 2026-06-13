from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

    from chat_lms_agent.record_types import RecordField, RecordType
    from chat_lms_agent.state import JsonValue

_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BOOL_STRINGS: Final = frozenset({"true", "false"})


def validate_record_values(
    record_type: RecordType,
    values: dict[str, JsonValue],
) -> list[str]:
    errors: list[str] = [
        f"missing required field: {field.name}"
        for field in record_type.fields
        if field.required and _is_empty(values.get(field.name))
    ]
    field_by_name = {field.name: field for field in record_type.fields}
    for name, value in values.items():
        field = field_by_name.get(name)
        if field is None:
            errors.append(f"unknown field: {name}")
            continue
        error = _value_error(field, value)
        if error is not None:
            errors.append(error)
    return errors


def _is_empty(value: JsonValue | None) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _enum_error(field: RecordField, value: JsonValue) -> str | None:
    if isinstance(value, str) and value in field.options:
        return None
    allowed = ", ".join(field.options)
    return f"{field.name} must be one of {allowed}"


def _date_error(field: RecordField, value: JsonValue) -> str | None:
    if isinstance(value, str) and _DATE_PATTERN.match(value) is not None:
        return None
    return f"{field.name} must be a date (YYYY-MM-DD)"


def _number_error(field: RecordField, value: JsonValue) -> str | None:
    return None if _is_number(value) else f"{field.name} must be a number"


def _bool_error(field: RecordField, value: JsonValue) -> str | None:
    return None if _is_bool(value) else f"{field.name} must be a boolean"


def _string_error(field: RecordField, value: JsonValue) -> str | None:
    return None if isinstance(value, str) else f"{field.name} must be a string"


_CHECKERS: Final[dict[str, Callable[[RecordField, JsonValue], str | None]]] = {
    "enum": _enum_error,
    "date": _date_error,
    "number": _number_error,
    "bool": _bool_error,
    "string": _string_error,
    "text": _string_error,
}


def _value_error(field: RecordField, value: JsonValue) -> str | None:
    if _is_empty(value):
        return None
    checker = _CHECKERS.get(field.field_type)
    if checker is None:
        return None
    return checker(field, value)


def _is_number(value: JsonValue) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        try:
            _ = float(value)
        except ValueError:
            return False
        return True
    return False


def _is_bool(value: JsonValue) -> bool:
    if isinstance(value, bool):
        return True
    return isinstance(value, str) and value.lower() in _BOOL_STRINGS
