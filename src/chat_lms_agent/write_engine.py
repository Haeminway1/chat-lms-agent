"""Transactional executor for compiled write-action templates."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeGuard, cast

from chat_lms_agent import classcard_db, journal
from chat_lms_agent.state import STATE_DIR, JsonValue
from chat_lms_agent.write_actions import PlanError, WriteActionTemplate, compile_plan

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from chat_lms_agent.state import ProfileState
    from chat_lms_agent.write_actions import CompiledStep, WriteStep


class ConnectFn(Protocol):
    def __call__(self, db_path: str | Path) -> sqlite3.Connection:
        """Open a SQLite connection with the repository's row-factory contract."""
        ...


type EnginePayload = dict[str, JsonValue]
type SqliteJsonValue = str | float | bytes | None


def run_write_action(  # noqa: PLR0913
    profile: ProfileState,
    template: WriteActionTemplate,
    params: dict[str, JsonValue],
    *,
    db_path: str | Path,
    connect: ConnectFn = classcard_db.connect,
    now: Callable[[], str] = lambda: datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ"),
) -> tuple[int, EnginePayload]:
    """Run one write-action template against a pinned profile database."""
    pinned = _pinned_db_path(profile, db_path)
    if pinned is None:
        return 4, {"status": "UNSAFE", "error_code": "DB_PATH_OUT_OF_PROFILE"}

    plan = compile_plan(template, params)
    if isinstance(plan, PlanError):
        return 2, {
            "status": "ERROR",
            "error_code": plan.code,
            "errors": list(plan.errors),
        }

    compiled_metadata = _compiled_step_metadata(template.steps, params)
    backup_path = _backup_path(profile, now())
    rows_affected: list[int] = []
    captures: dict[str, JsonValue] = {}

    with connect(pinned) as conn:
        if conn.isolation_level is None:
            conn.isolation_level = "DEFERRED"
        _ = conn.execute("PRAGMA foreign_keys = ON")
        _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copyfile(pinned, backup_path)
        _ = conn.execute("BEGIN IMMEDIATE")
        for index, step in enumerate(plan.steps):
            metadata = (
                compiled_metadata[index]
                if index < len(compiled_metadata)
                else _CompiledStepMetadata(f"step_{index + 1}", ())
            )
            result = _execute_step(conn, step, metadata.capture_refs, captures)
            match result:
                case _LookupMiss():
                    conn.rollback()
                    return 2, {
                        "status": "ERROR",
                        "error_code": "LOOKUP_MISS",
                        "step_id": metadata.step_id,
                    }
                case _WriteFailed():
                    conn.rollback()
                    return 2, {
                        "status": "ERROR",
                        "error_code": "WRITE_FAILED",
                        "step_id": metadata.step_id,
                    }
                case _StepOk(rowcount=rowcount):
                    rows_affected.append(rowcount)
        conn.commit()

    captured_ids = _captured_ids(captures)
    total_rows = sum(rows_affected)
    row_details: list[JsonValue] = []
    row_details.extend(rows_affected)
    details: dict[str, JsonValue] = {
        "action_id": template.template_id,
        "rows_affected_per_step": row_details,
        "captured_ids": captured_ids,
    }
    _ = journal.write_audit(
        profile,
        "write_action",
        "write action committed",
        details,
    )
    _ = journal.write_trace(
        profile,
        "write_action",
        "write action committed",
        details,
    )
    return 0, {
        "status": "PASS",
        "rows_affected": total_rows,
        "captured_ids": captured_ids,
        "backup": str(backup_path),
    }


@dataclass(frozen=True, slots=True)
class _StepOk:
    rowcount: int


@dataclass(frozen=True, slots=True)
class _LookupMiss:
    pass


@dataclass(frozen=True, slots=True)
class _WriteFailed:
    pass


@dataclass(frozen=True, slots=True)
class _CompiledStepMetadata:
    step_id: str
    capture_refs: tuple[str | None, ...]


type StepResult = _StepOk | _LookupMiss | _WriteFailed


def _execute_step(
    conn: sqlite3.Connection,
    step: CompiledStep,
    capture_refs: Sequence[str | None],
    captures: dict[str, JsonValue],
) -> StepResult:
    try:
        binds = _substituted_binds(step.bind_order, capture_refs, captures)
        if binds is None:
            return _WriteFailed()
        cursor = conn.execute(step.sql_text, binds)
        rowcount = max(cursor.rowcount, 0)
        capture_result = _capture_step_values(cursor, step, captures)
    except (sqlite3.Error, KeyError, IndexError):
        return _WriteFailed()
    match capture_result:
        case _LookupMiss():
            return capture_result
        case _StepOk():
            return _StepOk(rowcount)
        case _WriteFailed():
            return capture_result


def _capture_step_values(
    cursor: sqlite3.Cursor,
    step: CompiledStep,
    captures: dict[str, JsonValue],
) -> StepResult:
    column_captures = {
        name: source for name, source in step.captures.items() if source != "lastrowid"
    }
    for name, source in step.captures.items():
        if source == "lastrowid":
            captures[name] = cursor.lastrowid
    if not column_captures:
        return _StepOk(0)
    raw_row = cast("sqlite3.Row | None", cursor.fetchone())
    if raw_row is None:
        return _LookupMiss()
    for name, source in column_captures.items():
        raw_value = cast("JsonValue | bytes", raw_row[source])
        if not _is_sqlite_json_value(raw_value):
            return _WriteFailed()
        captures[name] = _json_value(raw_value)
    return _StepOk(0)


def _substituted_binds(
    bind_order: Sequence[JsonValue],
    capture_refs: Sequence[str | None],
    captures: dict[str, JsonValue],
) -> tuple[JsonValue, ...] | None:
    values: list[JsonValue] = []
    for index, value in enumerate(bind_order):
        capture_name = capture_refs[index] if index < len(capture_refs) else None
        if capture_name is not None:
            if capture_name not in captures:
                return None
            values.append(captures[capture_name])
            continue
        values.append(value)
    return tuple(values)


def _compiled_step_metadata(
    steps: Sequence[WriteStep],
    params: dict[str, JsonValue],
) -> tuple[_CompiledStepMetadata, ...]:
    metadata: list[_CompiledStepMetadata] = []
    produced: set[str] = set()
    for step in steps:
        fanout = _fanout_count((*step.match.values(), *step.set.values()), params)
        match step.op:
            case "resolve":
                refs = _binding_capture_refs(step.match.values(), produced)
                metadata.extend(
                    _CompiledStepMetadata(step.step_id, refs) for _index in range(fanout)
                )
            case "insert":
                refs = _binding_capture_refs(step.set.values(), produced)
                metadata.extend(
                    _CompiledStepMetadata(step.step_id, refs) for _index in range(fanout)
                )
            case "ensure":
                set_refs = _binding_capture_refs(step.set.values(), produced)
                match_refs = _binding_capture_refs(step.match.values(), produced)
                for _index in range(fanout):
                    metadata.append(_CompiledStepMetadata(step.step_id, set_refs))
                    metadata.append(_CompiledStepMetadata(step.step_id, match_refs))
            case "update_stub":
                refs = (
                    *_binding_capture_refs(step.set.values(), produced),
                    *_binding_capture_refs(step.match.values(), produced),
                )
                metadata.extend(
                    _CompiledStepMetadata(step.step_id, refs) for _index in range(fanout)
                )
            case _:
                metadata.extend(_CompiledStepMetadata(step.step_id, ()) for _index in range(fanout))
        produced.update(step.bind_result)
    return tuple(metadata)


def _binding_capture_refs(
    bindings: Iterable[str],
    produced: set[str],
) -> tuple[str | None, ...]:
    refs: list[str | None] = []
    for binding in bindings:
        capture_name = binding[1:] if binding.startswith("@") else ""
        refs.append(capture_name if capture_name in produced else None)
    return tuple(refs)


def _fanout_count(bindings: Sequence[str], params: dict[str, JsonValue]) -> int:
    for binding in bindings:
        if not binding.startswith("$"):
            continue
        head = binding[1:].split(".", maxsplit=1)[0]
        if not head.endswith("[]"):
            continue
        raw = params.get(head[:-2])
        if isinstance(raw, list):
            return len(raw)
    return 1


def _pinned_db_path(profile: ProfileState, db_path: str | Path) -> Path | None:
    resolved = Path(db_path).resolve()
    data_root = (profile.root / "data").resolve()
    repo_root = profile.repo_root.resolve()
    if not _is_under(resolved, data_root):
        return None
    if _is_under(resolved, repo_root):
        return None
    return resolved


def _backup_path(profile: ProfileState, stamp: str) -> Path:
    return profile.root / STATE_DIR / "write-actions" / "backups" / f"{stamp}.sqlite3"


def _is_under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _is_sqlite_json_value(value: JsonValue | bytes) -> TypeGuard[SqliteJsonValue]:
    return isinstance(value, str | int | float | bytes) or value is None


def _json_value(value: SqliteJsonValue) -> JsonValue:
    if isinstance(value, bytes):
        return value.hex()
    return value


def _captured_ids(captures: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        name: value
        for name, value in captures.items()
        if name.endswith("_id") and isinstance(value, int) and not isinstance(value, bool)
    }
