"""Pure write-action template loading and SQL plan compilation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, cast

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

WRITE_ACTION_SCHEMA_VERSION: Final = "write-action-v1"
REPO_WRITE_ACTIONS_DIR: Final = "write-actions"
PROFILE_WRITE_ACTIONS_DIR: Final = "write-actions"

type WriteActionSource = Literal["repo", "profile"]
type BindingMap = dict[str, str]
type ParamRule = dict[str, JsonValue]
type ParamSchema = dict[str, ParamRule]

_OPS: Final = frozenset({"resolve", "insert", "ensure", "update_stub"})
_PARAM_TYPES: Final = frozenset({"str", "int", "number", "bool", "date", "list", "dict"})
_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class WriteStep:
    step_id: str
    table: str
    op: str
    match: BindingMap
    set: BindingMap
    depends_on: tuple[str, ...]
    bind_result: BindingMap


@dataclass(frozen=True, slots=True)
class WriteActionTemplate:
    template_id: str
    schema_version: str
    summary: str
    route_id: str
    table_whitelist: tuple[str, ...]
    columns: dict[str, tuple[str, ...]]
    param_schema: ParamSchema
    steps: tuple[WriteStep, ...]
    source: WriteActionSource


@dataclass(frozen=True, slots=True)
class CompiledStep:
    sql_text: str
    bind_order: tuple[JsonValue, ...]
    captures: BindingMap


@dataclass(frozen=True, slots=True)
class CompiledPlan:
    steps: tuple[CompiledStep, ...]


@dataclass(frozen=True, slots=True)
class PlanError:
    code: str
    errors: tuple[str, ...]


def load_write_actions(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> tuple[list[WriteActionTemplate], list[str]]:
    """Load repo defaults then profile additions; profile wins by template id."""
    templates: dict[str, WriteActionTemplate] = {}
    warnings: list[str] = []
    _load_dir(repo_root / REPO_WRITE_ACTIONS_DIR, "repo", templates, warnings)
    if profile is not None:
        _load_dir(
            profile.root / STATE_DIR / PROFILE_WRITE_ACTIONS_DIR,
            "profile",
            templates,
            warnings,
        )
    return [templates[template_id] for template_id in sorted(templates)], warnings


def validate_template(template: WriteActionTemplate) -> list[str]:
    errors: list[str] = []
    produced: set[str] = set()
    seen_steps: set[str] = set()
    errors.extend(_identifier_errors(template))
    for name, rule in template.param_schema.items():
        errors.extend(_param_schema_errors(name, rule))
    for step in template.steps:
        step_errors = _step_errors(step, template, produced, seen_steps)
        errors.extend(step_errors)
        if _step_table_blocked(step, template):
            produced.update(step.bind_result)
            seen_steps.add(step.step_id)
            continue
        produced.update(step.bind_result)
        seen_steps.add(step.step_id)
    return errors


def _identifier_errors(template: WriteActionTemplate) -> list[str]:
    errors = [
        f"INVALID_TABLE_IDENTIFIER: {table}"
        for table in template.table_whitelist
        if not _valid_identifier(table)
    ]
    for table, columns in template.columns.items():
        if table not in template.table_whitelist:
            errors.append(f"COLUMNS_TABLE_NOT_WHITELISTED: {table}")
        errors.extend(
            f"INVALID_COLUMN_IDENTIFIER: {table}.{column}"
            for column in columns
            if not _valid_identifier(column)
        )
    return errors


def _step_errors(
    step: WriteStep,
    template: WriteActionTemplate,
    produced: set[str],
    seen_steps: set[str],
) -> list[str]:
    errors: list[str] = []
    if step.op not in _OPS:
        errors.append(f"INVALID_STEP_OP: {step.step_id}.{step.op}")
    if _step_table_blocked(step, template):
        errors.append(f"STEP_TABLE_NOT_WHITELISTED: {step.step_id}.{step.table}")
        return errors
    allowed_columns = template.columns.get(step.table, ())
    errors.extend(
        f"STEP_COLUMN_NOT_WHITELISTED: {step.step_id}.{step.table}.{column}"
        for column in (*step.match, *step.set)
        if column not in allowed_columns
    )
    errors.extend(
        f"UNKNOWN_STEP_DEPENDENCY: {step.step_id}.{dependency}"
        for dependency in step.depends_on
        if dependency not in seen_steps
    )
    errors.extend(
        f"UNKNOWN_CAPTURE_REF: {step.step_id}.{binding}"
        for binding in (*step.match.values(), *step.set.values())
        if binding.startswith("@") and binding[1:] not in produced
    )
    for capture, source in step.bind_result.items():
        if not capture.strip():
            errors.append(f"EMPTY_CAPTURE_NAME: {step.step_id}")
        if source != "lastrowid" and source not in allowed_columns:
            errors.append(f"CAPTURE_COLUMN_NOT_WHITELISTED: {step.step_id}.{source}")
        if not _valid_capture_source(step.op, source):
            errors.append(f"INVALID_CAPTURE_SOURCE: {step.step_id}.{source}")
    return errors


def _valid_capture_source(op: str, source: str) -> bool:
    match op:
        case "resolve" | "ensure":
            return source == "id"
        case "insert":
            return source == "lastrowid"
        case "update_stub":
            return False
        case _:
            return True


def _step_table_blocked(step: WriteStep, template: WriteActionTemplate) -> bool:
    return step.table not in template.table_whitelist


def compile_plan(
    template: WriteActionTemplate,
    params: dict[str, JsonValue],
) -> CompiledPlan | PlanError:
    """Compile a template to fixed parameterized SQL statement shapes."""
    template_errors = validate_template(template)
    if template_errors:
        return PlanError(code="INVALID_TEMPLATE", errors=tuple(template_errors))
    param_errors = _validate_params(template.param_schema, params)
    if param_errors:
        return PlanError(code="INVALID_PARAMS", errors=tuple(param_errors))
    compiled: list[CompiledStep] = []
    for step in template.steps:
        step_result = _compile_step(step, params)
        if isinstance(step_result, PlanError):
            return step_result
        compiled.extend(step_result)
    return CompiledPlan(steps=tuple(compiled))


def _load_dir(
    directory: Path,
    source: WriteActionSource,
    templates: dict[str, WriteActionTemplate],
    warnings: list[str],
) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.json")):
        template, warning = _parse_template(path, source)
        if warning is not None:
            warnings.append(warning)
            continue
        if template is not None:
            templates[template.template_id] = template


def _parse_template(
    path: Path,
    source: WriteActionSource,
) -> tuple[WriteActionTemplate | None, str | None]:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None, f"{path.name}: INVALID_JSON"
    if not isinstance(payload, dict):
        return None, f"{path.name}: NOT_AN_OBJECT"
    template, error = _template_from_payload(payload, source)
    if error is not None:
        return None, f"{path.name}: {error}"
    return template, None


def _template_from_payload(
    payload: dict[str, JsonValue],
    source: WriteActionSource,
) -> tuple[WriteActionTemplate | None, str | None]:
    if payload.get("schema_version") != WRITE_ACTION_SCHEMA_VERSION:
        return None, "UNSUPPORTED_SCHEMA_VERSION"
    if "sql" in payload:
        return None, "SQL_FIELD_NOT_ALLOWED"
    template_id = _string(payload.get("id"))
    if not template_id.strip():
        return None, "MISSING_ID"
    steps = _steps(payload.get("steps"))
    if steps is None:
        return None, "INVALID_STEPS"
    return (
        WriteActionTemplate(
            template_id=template_id.strip(),
            schema_version=WRITE_ACTION_SCHEMA_VERSION,
            summary=_string(payload.get("summary")),
            route_id=_string(payload.get("route_id")),
            table_whitelist=_string_tuple(payload.get("table_whitelist")),
            columns=_columns(payload.get("columns")),
            param_schema=_param_schema(payload.get("param_schema")),
            steps=steps,
            source=source,
        ),
        None,
    )


def _compile_step(
    step: WriteStep,
    params: dict[str, JsonValue],
) -> tuple[CompiledStep, ...] | PlanError:
    fanout = _fanout_count((*step.match.values(), *step.set.values()), params)
    if isinstance(fanout, PlanError):
        return fanout
    compiled: list[CompiledStep] = []
    for index in range(fanout):
        set_binds = _bindings(step.set, params, index)
        match_binds = _bindings(step.match, params, index)
        if isinstance(set_binds, PlanError):
            return set_binds
        if isinstance(match_binds, PlanError):
            return match_binds
        match step.op:
            case "resolve":
                sql = _select_sql(step.table, step.match)
                compiled.append(CompiledStep(sql, match_binds, dict(step.bind_result)))
            case "insert":
                columns = tuple(step.set)
                sql = _insert_sql(step.table, columns)
                compiled.append(CompiledStep(sql, set_binds, dict(step.bind_result)))
            case "ensure":
                columns = tuple(step.set)
                insert_sql = _insert_or_ignore_sql(step.table, columns)
                select_sql = _select_sql(step.table, step.match)
                compiled.append(CompiledStep(insert_sql, set_binds, {}))
                compiled.append(CompiledStep(select_sql, match_binds, dict(step.bind_result)))
            case "update_stub":
                sql = _update_sql(step.table, step.set, step.match)
                compiled.append(
                    CompiledStep(sql, (*set_binds, *match_binds), dict(step.bind_result)),
                )
            case _:
                return PlanError(code="INVALID_TEMPLATE", errors=(f"INVALID_STEP_OP: {step.op}",))
    return tuple(compiled)


def _validate_params(schema: ParamSchema, params: dict[str, JsonValue]) -> list[str]:
    errors: list[str] = []
    for name, rule in schema.items():
        value = params.get(name)
        required = rule.get("required") is True
        if value is None:
            if required:
                errors.append(f"MISSING_PARAM: {name}")
            continue
        expected_type = _string(rule.get("type")) or "str"
        if not _param_matches_type(value, expected_type):
            errors.append(f"INVALID_PARAM_TYPE: {name}")
            continue
        allowed = rule.get("enum")
        if isinstance(allowed, list) and value not in allowed:
            errors.append(f"INVALID_PARAM_ENUM: {name}")
        if expected_type == "date" and not _valid_date(value):
            errors.append(f"INVALID_PARAM_DATE: {name}")
        if not _in_numeric_range(value, rule):
            errors.append(f"INVALID_PARAM_RANGE: {name}")
    return errors


def _param_schema_errors(name: str, rule: ParamRule) -> list[str]:
    errors: list[str] = []
    expected_type = rule.get("type")
    if expected_type is not None and (
        not isinstance(expected_type, str) or expected_type not in _PARAM_TYPES
    ):
        errors.append(f"INVALID_PARAM_SCHEMA_TYPE: {name}")
    enum = rule.get("enum")
    if enum is not None and not isinstance(enum, list):
        errors.append(f"INVALID_PARAM_SCHEMA_ENUM: {name}")
    for key in ("min", "max"):
        boundary = rule.get(key)
        if boundary is not None and not _is_number(boundary):
            errors.append(f"INVALID_PARAM_SCHEMA_RANGE: {name}.{key}")
    return errors


def _bindings(
    bindings: BindingMap,
    params: dict[str, JsonValue],
    fanout_index: int,
) -> tuple[JsonValue, ...] | PlanError:
    values: list[JsonValue] = []
    for binding in bindings.values():
        value = _resolve_binding(binding, params, fanout_index)
        if isinstance(value, PlanError):
            return value
        values.append(value)
    return tuple(values)


def _resolve_binding(
    binding: str,
    params: dict[str, JsonValue],
    fanout_index: int,
) -> JsonValue | PlanError:
    if binding.startswith("='") and binding.endswith("'"):
        return binding[2:-1]
    if binding.startswith("@"):
        return binding
    if not binding.startswith("$"):
        return PlanError(code="INVALID_BINDING", errors=(f"INVALID_BINDING: {binding}",))
    path = binding[1:]
    return _resolve_param_path(path, params, fanout_index)


def _resolve_param_path(
    path: str,
    params: dict[str, JsonValue],
    fanout_index: int,
) -> JsonValue | PlanError:
    head, *tail = path.split(".")
    if head.endswith("[]"):
        name = head[:-2]
        raw_array = params.get(name)
        if not isinstance(raw_array, list):
            return PlanError(code="INVALID_BINDING", errors=(f"EXPECTED_ARRAY: {name}",))
        if fanout_index >= len(raw_array):
            return PlanError(code="INVALID_BINDING", errors=(f"ARRAY_INDEX_MISSING: {name}",))
        return _descend(raw_array[fanout_index], tail, path)
    if head not in params:
        return PlanError(code="INVALID_BINDING", errors=(f"UNKNOWN_PARAM: {head}",))
    return _descend(params[head], tail, path)


def _descend(value: JsonValue, path: list[str], original: str) -> JsonValue | PlanError:
    current = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return PlanError(code="INVALID_BINDING", errors=(f"UNKNOWN_PARAM_PATH: {original}",))
        current = current[key]
    return current


def _fanout_count(bindings: tuple[str, ...], params: dict[str, JsonValue]) -> int | PlanError:
    array_names: set[str] = set()
    for binding in bindings:
        name = _array_name(binding)
        if name is not None:
            array_names.add(name)
    if not array_names:
        return 1
    if len(array_names) != 1:
        return PlanError(code="INVALID_BINDING", errors=("MULTIPLE_ARRAY_FANOUTS",))
    name = next(iter(array_names))
    raw = params.get(name)
    if not isinstance(raw, list):
        return PlanError(code="INVALID_BINDING", errors=(f"EXPECTED_ARRAY: {name}",))
    return len(raw)


def _array_name(binding: str) -> str | None:
    if not binding.startswith("$"):
        return None
    head = binding[1:].split(".", maxsplit=1)[0]
    if not head.endswith("[]"):
        return None
    return head[:-2]


def _param_matches_type(value: JsonValue, expected_type: str) -> bool:
    match expected_type:
        case "str" | "date":
            matches = isinstance(value, str)
        case "int":
            matches = isinstance(value, int) and not isinstance(value, bool)
        case "number":
            matches = _is_number(value)
        case "bool":
            matches = isinstance(value, bool)
        case "list":
            matches = isinstance(value, list)
        case "dict":
            matches = isinstance(value, dict)
        case _:
            matches = False
    return matches


def _valid_date(value: JsonValue) -> bool:
    if not isinstance(value, str):
        return False
    try:
        _ = date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _in_numeric_range(value: JsonValue, rule: ParamRule) -> bool:
    numeric_value = _number(value)
    if numeric_value is None:
        return True
    minimum = rule.get("min")
    maximum = rule.get("max")
    numeric_minimum = _number(minimum)
    numeric_maximum = _number(maximum)
    if numeric_minimum is not None and numeric_value < numeric_minimum:
        return False
    return not (numeric_maximum is not None and numeric_value > numeric_maximum)


def _is_number(value: JsonValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: JsonValue) -> int | float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    return None


def _select_sql(table: str, match: BindingMap) -> str:
    return f"SELECT id FROM {table} WHERE {_where_clause(match)}"  # noqa: S608


def _insert_sql(table: str, columns: tuple[str, ...]) -> str:
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({_placeholders(columns)})"  # noqa: S608


def _insert_or_ignore_sql(table: str, columns: tuple[str, ...]) -> str:
    return (
        f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) "  # noqa: S608
        f"VALUES ({_placeholders(columns)})"
    )


def _update_sql(table: str, set_bindings: BindingMap, match_bindings: BindingMap) -> str:
    return f"UPDATE {table} SET {_set_clause(set_bindings)} WHERE {_where_clause(match_bindings)}"  # noqa: S608


def _set_clause(bindings: BindingMap) -> str:
    return ", ".join(f"{column} = ?" for column in bindings)


def _where_clause(bindings: BindingMap) -> str:
    return " AND ".join(f"{column} = ?" for column in bindings)


def _placeholders(columns: tuple[str, ...]) -> str:
    return ", ".join("?" for _column in columns)


def _valid_identifier(value: str) -> bool:
    return _IDENTIFIER_RE.fullmatch(value) is not None


def _steps(value: JsonValue | None) -> tuple[WriteStep, ...] | None:
    if not isinstance(value, list):
        return None
    steps: list[WriteStep] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        if "sql" in item:
            return None
        step_id = _string(item.get("step_id"))
        table = _string(item.get("table"))
        op = _string(item.get("op"))
        if not step_id or not table or not op:
            return None
        steps.append(
            WriteStep(
                step_id=step_id,
                table=table,
                op=op,
                match=_binding_map(item.get("match")),
                set=_binding_map(item.get("set")),
                depends_on=_string_tuple(item.get("depends_on")),
                bind_result=_binding_map(item.get("bind_result")),
            ),
        )
    return tuple(steps)


def _columns(value: JsonValue | None) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        return {}
    columns: dict[str, tuple[str, ...]] = {}
    for table, raw_columns in value.items():
        columns[table] = _string_tuple(raw_columns)
    return columns


def _param_schema(value: JsonValue | None) -> ParamSchema:
    if not isinstance(value, dict):
        return {}
    schema: ParamSchema = {}
    for name, rule in value.items():
        if isinstance(rule, dict):
            schema[name] = dict(rule)
    return schema


def _binding_map(value: JsonValue | None) -> BindingMap:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(item, str) and key.strip() and item.strip()
    }


def _string(value: JsonValue | None) -> str:
    if isinstance(value, str):
        return value
    return ""


def _string_tuple(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())
