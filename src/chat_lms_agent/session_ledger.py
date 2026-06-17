"""Host session transcript ledger.

Structural reference: ``self_qa.py`` (append-only JSONL, byte-bounded) and
``journal.py`` (runtime redaction). The host already writes a full per-session
transcript (a rollout JSONL whose location the host adapter knows); this module
ingests that transcript into a durable, owner-facing review log under the
private profile workspace so the operator can audit, after the fact, what the
teacher asked, how the agent narrated and sequenced tools, every tool call with
its arguments and output, token usage, and the per-turn model/approval posture.

Privacy invariants. All state lives under ``profile.root / STATE_DIR /
session-logs`` and never enters the public repo (``resolve_profile_state``
rejects repo roots). Every persisted free-text field passes through
``journal.redact_runtime_text`` (secret/token/absolute-path redaction, then
learner-PII pseudonymization). Names are restored only on owner-facing
``show``/``export --reveal`` via ``privacy.restore_text``. The agent's private
reasoning may be encrypted by the host and is then recorded as a marker only.

Safety invariants. Ingest is idempotent (per-file line-offset checkpoint),
incremental, serialized by an exclusive-create lock, retention/size bounded, and
never raises out of the trigger path.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast, final

from chat_lms_agent.hosts import SESSION_TRANSCRIPT_GLOB, session_transcript_dirs
from chat_lms_agent.journal import redact_runtime_text
from chat_lms_agent.privacy import restore_text
from chat_lms_agent.state import (
    STATE_DIR,
    read_state_mapping,
    write_state_mapping,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

SESSION_LEDGER_SCHEMA_VERSION: Final = "session-ledger-v1"
SESSION_LOGS_DIR: Final = "session-logs"
INGEST_STATE_RELATIVE: Final = f"{SESSION_LOGS_DIR}/_ingest-state.json"
INGEST_LOCK_FILE: Final = "_ingest.lock"

FIELD_MAX_CHARS: Final = 4_000
INGEST_MAX_LINES_PER_RUN: Final = 20_000
SESSION_FILE_MAX_BYTES: Final = 4_194_304
MAX_SESSION_FILES: Final = 300
LOCK_STALE_SECONDS: Final = 120.0

_FREE_TEXT_FIELDS: Final = ("text", "tool_args", "tool_output", "cwd")
_UUID_RE: Final = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
)
_ERROR_OUTPUT_RE: Final = re.compile(
    r"""(?ix)
    (?: exit[ _]?code ["']? [ :=]+ ["']? [1-9] )   # exit code: 1 / "exit_code": 1
    | (?: "success" \s* : \s* false )               # structured failure
    | (?: "is_?error" \s* : \s* true )
    """,
)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def is_enabled(profile: ProfileState) -> bool:
    """Report whether ingest is on (default on; only explicit ``enabled: false`` is off)."""
    return read_state_mapping(profile, INGEST_STATE_RELATIVE).get("enabled") is not False


def set_enabled(profile: ProfileState, *, enabled: bool) -> dict[str, JsonValue]:
    state = read_state_mapping(profile, INGEST_STATE_RELATIVE)
    state["enabled"] = enabled
    state["schema_version"] = SESSION_LEDGER_SCHEMA_VERSION
    write_state_mapping(profile, INGEST_STATE_RELATIVE, state)
    return {"status": "PASS", "enabled": enabled}


def ingest_rollouts(
    profile: ProfileState,
    *,
    transcript_home: str | None = None,
) -> dict[str, JsonValue]:
    """Ingest new transcript lines into the per-session logs. Never raises."""
    try:
        return _ingest_guarded(profile, transcript_home)
    except (OSError, ValueError, TypeError, KeyError, JSONDecodeError) as error:
        return {
            "status": "ERROR",
            "error_code": "INGEST_FAILED",
            "message": _safe_message(profile, error),
        }


def _ingest_guarded(profile: ProfileState, transcript_home: str | None) -> dict[str, JsonValue]:
    if _under_repo(profile):
        # Defense in depth: a transcript log must never land in the public repo,
        # even via the --profile fixture form that skips resolve_profile_state.
        return {"status": "PASS", "skipped": "repo-root"}
    if not is_enabled(profile):
        return {"status": "PASS", "skipped": "disabled"}
    sessions_dir = _locate_sessions_dir(profile, transcript_home)
    if sessions_dir is None:
        return {"status": "PASS", "skipped": "no-sessions-dir", "sessions_ingested": 0}
    if not _acquire_lock(profile):
        return {"status": "PASS", "skipped": "locked", "sessions_ingested": 0}
    try:
        return _ingest_locked(profile, sessions_dir)
    finally:
        _release_lock(profile)


def _under_repo(profile: ProfileState) -> bool:
    return profile.root == profile.repo_root or profile.repo_root in profile.root.parents


def _safe_message(profile: ProfileState, error: Exception) -> str:
    try:
        return redact_runtime_text(profile, str(error))[:200]
    except (OSError, ValueError, TypeError):
        return "ingest error"


def list_sessions(profile: ProfileState) -> dict[str, JsonValue]:
    state = read_state_mapping(profile, INGEST_STATE_RELATIVE)
    raw = state.get("sessions")
    sessions: list[JsonValue] = []
    if isinstance(raw, dict):
        sessions = [info for info in raw.values() if isinstance(info, dict)]
    sessions.sort(key=_session_sort_key, reverse=True)
    return {
        "status": "PASS",
        "schema_version": SESSION_LEDGER_SCHEMA_VERSION,
        "enabled": is_enabled(profile),
        "session_count": len(sessions),
        "sessions": sessions,
    }


def show_session(profile: ProfileState, session_id: str) -> tuple[int, dict[str, JsonValue]]:
    """Owner-facing read: pseudonyms restored to real names via a local lookup."""
    return _read_session(profile, session_id, reveal=True)


def export_session(
    profile: ProfileState,
    session_id: str,
    *,
    reveal: bool = False,
) -> tuple[int, dict[str, JsonValue]]:
    """Export one session; pseudonyms are kept by default so it is safe to share."""
    return _read_session(profile, session_id, reveal=reveal)


# --------------------------------------------------------------------------- #
# Ingest internals
# --------------------------------------------------------------------------- #
def _ingest_locked(profile: ProfileState, sessions_dir: Path) -> dict[str, JsonValue]:
    state = read_state_mapping(profile, INGEST_STATE_RELATIVE)
    ledger = _LedgerState(
        offsets=_string_int_map(state.get("offsets")),
        sessions=_mapping(state.get("sessions")),
    )
    budget = INGEST_MAX_LINES_PER_RUN
    appended = 0
    touched: set[str] = set()
    # Newest session first so the just-finished session is current even when an
    # old backlog is still draining under the per-run budget.
    rollouts = sorted(sessions_dir.glob(f"**/{SESSION_TRANSCRIPT_GLOB}"), key=_mtime, reverse=True)
    present = {rollout.relative_to(sessions_dir).as_posix() for rollout in rollouts}
    for rel in [key for key in ledger.offsets if key not in present]:
        del ledger.offsets[rel]
    for rollout in rollouts:
        if budget <= 0:
            break
        rel = rollout.relative_to(sessions_dir).as_posix()
        added = _ingest_one_file(profile, rollout, rel, ledger, budget)
        if added.records:
            touched.add(added.session_id)
        appended += added.records
        budget -= added.consumed
    _prune_retention(profile, ledger.sessions)
    write_state_mapping(
        profile,
        INGEST_STATE_RELATIVE,
        {
            "schema_version": SESSION_LEDGER_SCHEMA_VERSION,
            "enabled": True,
            "last_ingest_at": time.time(),
            "offsets": cast("JsonValue", ledger.offsets),
            "sessions": cast("JsonValue", ledger.sessions),
        },
    )
    return {
        "status": "PASS",
        "sessions_ingested": len(touched),
        "records_appended": appended,
    }


@dataclass(slots=True)
class _LedgerState:
    offsets: dict[str, int]
    sessions: dict[str, JsonValue]


@final
class _FileIngest:
    __slots__ = ("consumed", "records", "session_id")

    def __init__(self, session_id: str, records: int, consumed: int) -> None:
        self.session_id = session_id
        self.records = records
        self.consumed = consumed


def _ingest_one_file(
    profile: ProfileState,
    rollout: Path,
    rel: str,
    ledger: _LedgerState,
    budget: int,
) -> _FileIngest:
    session_id = _session_id_from_filename(rollout.name)
    start = ledger.offsets.get(rel, 0)
    lines, new_offset = _read_new_complete_lines(rollout, start, budget)
    if not lines:
        ledger.offsets[rel] = new_offset
        return _FileIngest(session_id, 0, 0)
    records: list[dict[str, JsonValue]] = []
    summary = _SessionSummary.from_index(ledger.sessions.get(session_id), session_id, rel)
    for raw in lines:
        normalized = _normalize_line(raw, session_id)
        if normalized is None:
            continue
        redacted = _redact_record(profile, normalized)
        records.append(redacted)
        summary.observe(redacted)
    written = _append_records(profile, session_id, records)
    summary.truncated = summary.truncated or written < len(records)
    summary.record_count += written
    ledger.sessions[session_id] = summary.to_index()
    ledger.offsets[rel] = new_offset
    return _FileIngest(session_id, written, len(lines))


def _read_new_complete_lines(path: Path, byte_offset: int, budget: int) -> tuple[list[str], int]:
    # Byte-offset based: a fully-ingested file (offset == size) costs one stat()
    # and no read, so re-globbing a large history stays cheap. Only complete
    # lines (ending in a newline byte, always a UTF-8 boundary) are consumed, so
    # a line still being written is held back until its newline arrives.
    try:
        size = path.stat().st_size
    except OSError:
        return [], byte_offset
    if byte_offset >= size:
        return [], byte_offset
    try:
        with path.open("rb") as handle:
            _ = handle.seek(byte_offset)
            chunk = handle.read()
    except OSError:
        return [], byte_offset
    text = chunk.decode("utf-8", errors="replace")
    cut = text.rfind("\n")
    if cut == -1:
        return [], byte_offset
    complete = text[: cut + 1]
    lines = complete.split("\n")[:-1]
    if len(lines) > budget:
        kept = lines[:budget]
        consumed = ("\n".join(kept) + "\n").encode("utf-8")
        return kept, byte_offset + len(consumed)
    return lines, byte_offset + len(complete.encode("utf-8"))


def _append_records(
    profile: ProfileState,
    session_id: str,
    records: list[dict[str, JsonValue]],
) -> int:
    if not records:
        return 0
    path = _session_path(profile, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= SESSION_FILE_MAX_BYTES:
        return 0
    blob = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(blob)
    return len(records)


def _prune_retention(profile: ProfileState, sessions: dict[str, JsonValue]) -> None:
    logs_dir = _logs_dir(profile)
    if not logs_dir.exists():
        return
    files = sorted(
        logs_dir.glob("*.jsonl"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    for stale in files[MAX_SESSION_FILES:]:
        with contextlib.suppress(OSError):
            stale.unlink()
        _ = sessions.pop(stale.stem, None)


# --------------------------------------------------------------------------- #
# Normalization (rollout JSONL -> fixed-field record)
# --------------------------------------------------------------------------- #
def _normalize_line(raw: str, session_id: str) -> dict[str, JsonValue] | None:
    obj = _parse_line(raw)
    if obj is None:
        return None
    payload = obj.get("payload")
    payload_map: dict[str, JsonValue] = payload if isinstance(payload, dict) else {}
    timestamp = obj.get("timestamp")
    record = _blank_record(session_id, timestamp if isinstance(timestamp, str) else None)
    line_type = obj.get("type")
    if line_type == "session_meta":
        return _fill_session_meta(record, payload_map)
    if line_type == "turn_context":
        return _fill_turn_context(record, payload_map)
    if line_type == "event_msg":
        return _fill_event_msg(record, payload_map)
    if line_type == "response_item":
        return _fill_response_item(record, payload_map)
    return None


def _parse_line(raw: str) -> dict[str, JsonValue] | None:
    if not raw.strip():
        return None
    try:
        obj = cast("JsonValue", json.loads(raw))
    except JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _blank_record(session_id: str, timestamp: str | None) -> dict[str, JsonValue]:
    return {
        "schema_version": SESSION_LEDGER_SCHEMA_VERSION,
        "session_id": session_id,
        "ts": timestamp,
        "kind": None,
        "text": None,
        "tool_name": None,
        "tool_args": None,
        "tool_output": None,
        "call_id": None,
        "model": None,
        "approval": None,
        "sandbox": None,
        "effort": None,
        "tokens": None,
        "cwd": None,
        "encrypted": False,
        "truncated": False,
    }


def _fill_session_meta(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "session_meta"
    record["cwd"] = _as_text(payload.get("cwd"))
    record["text"] = _session_meta_summary(payload)
    return record


def _fill_turn_context(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "turn_context"
    record["model"] = _as_text(payload.get("model"))
    record["cwd"] = _as_text(payload.get("cwd"))
    record["approval"] = _as_text(payload.get("approval_policy"))
    record["sandbox"] = _sandbox_label(payload.get("sandbox_policy"))
    record["effort"] = _as_text(payload.get("effort"))
    return record


def _fill_event_msg(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue] | None:
    event_type = payload.get("type")
    filler = _EVENT_FILLERS.get(event_type) if isinstance(event_type, str) else None
    if filler is None:
        return _fill_other(record, "event", event_type, payload)
    return filler(record, payload)


def _fill_response_item(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue] | None:
    item_type = payload.get("type")
    filler = _RESPONSE_FILLERS.get(item_type) if isinstance(item_type, str) else None
    if filler is None:
        return _fill_other(record, "response", item_type, payload)
    return filler(record, payload)


def _fill_user_message(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "user_prompt"
    record["text"] = _as_text(payload.get("message"))
    return record


def _fill_agent_message(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "agent_message"
    record["text"] = _as_text(payload.get("message"))
    return record


def _fill_token_count(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue] | None:
    tokens = _extract_tokens(payload.get("info"))
    if tokens is None:
        return None  # the first per-turn emit carries no usage; skip the noise.
    record["kind"] = "usage"
    record["tokens"] = tokens
    return record


def _fill_agent_reasoning(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "reasoning"
    record["text"] = _as_text(payload.get("text"))
    return record


def _fill_message(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = _role_kind(payload.get("role"))
    record["text"] = _join_content(payload.get("content"))
    return record


def _fill_reasoning(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "reasoning"
    summary = _join_content(payload.get("summary"))
    if summary is None:
        # The host encrypts the chain-of-thought; only a marker survives.
        record["encrypted"] = True
    else:
        record["text"] = summary
    return record


def _fill_function_call(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return _set_tool_call(record, payload, args_key="arguments")


def _fill_custom_tool_call(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return _set_tool_call(record, payload, args_key="input")


def _fill_tool_output(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "tool_output"
    record["call_id"] = _as_text(payload.get("call_id"))
    record["tool_output"] = _stringify_output(_first_present(payload, "output", "results"))
    return record


def _fill_search_call(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "tool_call"
    record["tool_name"] = _as_text(payload.get("type"))
    record["call_id"] = _as_text(payload.get("call_id"))
    arguments = payload.get("arguments")
    record["tool_args"] = _stringify_output(arguments) if arguments is not None else None
    return record


def _fill_mcp_tool_call(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "tool_call"
    record["call_id"] = _as_text(payload.get("call_id"))
    invocation = payload.get("invocation")
    if isinstance(invocation, dict):
        server = _as_text(invocation.get("server")) or ""
        tool = _as_text(invocation.get("tool")) or ""
        record["tool_name"] = f"{server}.{tool}".strip(".") or "mcp"
        record["tool_args"] = _stringify_output(invocation.get("arguments"))
    else:
        record["tool_name"] = "mcp"
    record["tool_output"] = _stringify_output(payload.get("result"))
    return record


def _fill_patch_apply(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "tool_output"
    record["tool_name"] = "apply_patch"
    record["call_id"] = _as_text(payload.get("call_id"))
    changes = payload.get("changes")
    files = ", ".join(str(key) for key in changes) if isinstance(changes, dict) else ""
    summary: dict[str, JsonValue] = {
        "success": payload.get("success"),
        "stdout": payload.get("stdout"),
        "stderr": payload.get("stderr"),
        "files": files,
    }
    record["tool_output"] = _stringify_output(summary)
    return record


def _fill_exec_end(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    record["kind"] = "tool_output"
    record["tool_name"] = "exec"
    record["call_id"] = _as_text(payload.get("call_id"))
    record["tool_output"] = _stringify_output(
        {
            "command": payload.get("command"),
            "exit_code": payload.get("exit_code"),
            "stdout": payload.get("stdout"),
            "stderr": payload.get("stderr"),
        },
    )
    return record


def _fill_other(
    record: dict[str, JsonValue],
    family: str,
    label: JsonValue,
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    # Catch-all so a future host event type is recorded, never silently lost.
    name = _as_text(label) or "unknown"
    record["kind"] = "other"
    record["tool_name"] = f"{family}:{name}"
    record["text"] = _stringify_output(payload)
    return record


def _set_tool_call(
    record: dict[str, JsonValue],
    payload: dict[str, JsonValue],
    *,
    args_key: str,
) -> dict[str, JsonValue]:
    record["kind"] = "tool_call"
    record["tool_name"] = _as_text(payload.get("name"))
    record["tool_args"] = _stringify_output(payload.get(args_key))
    record["call_id"] = _as_text(payload.get("call_id"))
    return record


type _Filler = Callable[[dict[str, JsonValue], dict[str, JsonValue]], dict[str, JsonValue] | None]

_EVENT_FILLERS: Final[dict[str, _Filler]] = {
    "user_message": _fill_user_message,
    "agent_message": _fill_agent_message,
    "token_count": _fill_token_count,
    "agent_reasoning": _fill_agent_reasoning,
    "exec_command_end": _fill_exec_end,
    "patch_apply_end": _fill_patch_apply,
    "mcp_tool_call_end": _fill_mcp_tool_call,
}

_RESPONSE_FILLERS: Final[dict[str, _Filler]] = {
    "message": _fill_message,
    "reasoning": _fill_reasoning,
    "function_call": _fill_function_call,
    "function_call_output": _fill_tool_output,
    "custom_tool_call": _fill_custom_tool_call,
    "custom_tool_call_output": _fill_tool_output,
    "tool_search_call": _fill_search_call,
    "tool_search_output": _fill_tool_output,
    "web_search_call": _fill_search_call,
    "image_generation_call": _fill_search_call,
}


def _redact_record(
    profile: ProfileState,
    record: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    redacted = dict(record)
    truncated = record.get("truncated") is True
    for field in _FREE_TEXT_FIELDS:
        value = redacted.get(field)
        if not isinstance(value, str):
            continue
        if len(value) > FIELD_MAX_CHARS:
            truncated = True
        capped = value[:FIELD_MAX_CHARS]
        redacted[field] = redact_runtime_text(profile, capped)[:FIELD_MAX_CHARS]
    redacted["truncated"] = truncated
    return redacted


# --------------------------------------------------------------------------- #
# Read / restore
# --------------------------------------------------------------------------- #
def _read_session(
    profile: ProfileState,
    session_id: str,
    *,
    reveal: bool,
) -> tuple[int, dict[str, JsonValue]]:
    path = _session_path(profile, session_id)
    if not path.exists():
        return 2, {"status": "ERROR", "error_code": "SESSION_NOT_FOUND"}
    records: list[JsonValue] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = cast("JsonValue", json.loads(line))
        except JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(_restore_record(profile, payload) if reveal else payload)
    return 0, {
        "status": "PASS",
        "schema_version": SESSION_LEDGER_SCHEMA_VERSION,
        "session_id": session_id,
        "record_count": len(records),
        "records": records,
    }


def _restore_record(profile: ProfileState, record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    restored = dict(record)
    for field in _FREE_TEXT_FIELDS:
        value = restored.get(field)
        if isinstance(value, str):
            restored[field] = restore_text(profile, value)
    return restored


# --------------------------------------------------------------------------- #
# Session summary accounting
# --------------------------------------------------------------------------- #
@final
class _SessionSummary:
    __slots__ = (
        "cwd",
        "error_count",
        "last_ts",
        "model",
        "prompt_count",
        "record_count",
        "rollout_file",
        "session_id",
        "started_at",
        "tool_count",
        "truncated",
    )

    def __init__(self, session_id: str, rollout_file: str) -> None:
        self.session_id = session_id
        self.rollout_file = rollout_file
        self.started_at: str | None = None
        self.last_ts: str | None = None
        self.cwd: str | None = None
        self.model: str | None = None
        self.prompt_count = 0
        self.tool_count = 0
        self.error_count = 0
        self.record_count = 0
        self.truncated = False

    @classmethod
    def from_index(
        cls,
        existing: JsonValue,
        session_id: str,
        rollout_file: str,
    ) -> _SessionSummary:
        summary = cls(session_id, rollout_file)
        if not isinstance(existing, dict):
            return summary
        summary.started_at = _opt_text(existing.get("started_at"))
        summary.last_ts = _opt_text(existing.get("last_ts"))
        summary.cwd = _opt_text(existing.get("cwd"))
        summary.model = _opt_text(existing.get("model"))
        summary.prompt_count = _opt_int(existing.get("prompt_count"))
        summary.tool_count = _opt_int(existing.get("tool_count"))
        summary.error_count = _opt_int(existing.get("error_count"))
        summary.record_count = _opt_int(existing.get("record_count"))
        summary.truncated = existing.get("truncated") is True
        return summary

    def observe(self, record: dict[str, JsonValue]) -> None:
        kind = record.get("kind")
        timestamp = record.get("ts")
        if isinstance(timestamp, str):
            if self.started_at is None:
                self.started_at = timestamp
            self.last_ts = timestamp
        if kind == "user_prompt":
            self.prompt_count += 1
        elif kind == "tool_call":
            self.tool_count += 1
        elif kind == "tool_output" and _looks_like_error(record.get("tool_output")):
            self.error_count += 1
        elif kind == "turn_context":
            self.model = _opt_text(record.get("model")) or self.model
        if self.cwd is None:
            self.cwd = _opt_text(record.get("cwd"))

    def to_index(self) -> dict[str, JsonValue]:
        return {
            "session_id": self.session_id,
            "rollout_file": self.rollout_file,
            "started_at": self.started_at,
            "last_ts": self.last_ts,
            "cwd": self.cwd,
            "model": self.model,
            "prompt_count": self.prompt_count,
            "tool_count": self.tool_count,
            "error_count": self.error_count,
            "record_count": self.record_count,
            "truncated": self.truncated,
        }


# --------------------------------------------------------------------------- #
# Locator + lock + small helpers
# --------------------------------------------------------------------------- #
def _locate_sessions_dir(profile: ProfileState, transcript_home: str | None) -> Path | None:
    # The host adapter owns the candidate locations; an explicit home is
    # authoritative there, so tests and triggers never ingest unrelated
    # transcripts from a machine-wide default home.
    for candidate in session_transcript_dirs(profile.root, transcript_home):
        if candidate.is_dir():
            return candidate
    return None


def _acquire_lock(profile: ProfileState) -> bool:
    path = _lock_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = _try_create_lock(path)
    if descriptor is None and _lock_is_stale(path):
        with contextlib.suppress(OSError):
            path.unlink()
        descriptor = _try_create_lock(path)
    if descriptor is None:
        return False
    try:
        _ = os.write(descriptor, str(time.time()).encode("utf-8"))
    finally:
        os.close(descriptor)
    return True


def _try_create_lock(path: Path) -> int | None:
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        return None


def _lock_is_stale(path: Path) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age > LOCK_STALE_SECONDS


def _release_lock(profile: ProfileState) -> None:
    with contextlib.suppress(OSError):
        _lock_path(profile).unlink()


def _session_id_from_filename(name: str) -> str:
    match = _UUID_RE.search(name)
    if match is not None:
        return match.group(0)
    return _sanitize_session_id(name.removesuffix(".jsonl"))


def _sanitize_session_id(session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:64]
    return cleaned or "default"


def _session_meta_summary(payload: dict[str, JsonValue]) -> str:
    git = payload.get("git")
    branch = git.get("branch") if isinstance(git, dict) else None
    commit = git.get("commit_hash") if isinstance(git, dict) else None
    parts = [
        f"originator={_as_text(payload.get('originator')) or ''}",
        f"cli_version={_as_text(payload.get('cli_version')) or ''}",
        f"branch={_as_text(branch) or ''}",
        f"commit={_as_text(commit) or ''}",
    ]
    return " ".join(parts)


def _sandbox_label(value: JsonValue) -> str | None:
    if isinstance(value, dict):
        return _as_text(value.get("type"))
    return _as_text(value)


def _join_content(content: JsonValue) -> str | None:
    if not isinstance(content, list):
        return None
    texts = [item.get("text") for item in content if isinstance(item, dict)]
    joined = "\n".join(text for text in texts if isinstance(text, str))
    return joined or None


def _stringify_output(output: JsonValue) -> str | None:
    if output is None:
        return None
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=False, sort_keys=True)


def _first_present(payload: dict[str, JsonValue], *keys: str) -> JsonValue:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _extract_tokens(info: JsonValue) -> dict[str, JsonValue] | None:
    if not isinstance(info, dict):
        return None
    total = info.get("total_token_usage")
    if not isinstance(total, dict):
        return None
    fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    )
    tokens: dict[str, JsonValue] = {}
    for field in fields:
        value = total.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            tokens[field] = value
    return tokens or None


def _looks_like_error(value: JsonValue) -> bool:
    return isinstance(value, str) and _ERROR_OUTPUT_RE.search(value) is not None


def _role_kind(role: JsonValue) -> str:
    if role == "assistant":
        return "agent_message"
    if role == "developer":
        return "developer_context"
    return "user_prompt"


def _as_text(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _opt_text(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _opt_int(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _string_int_map(value: JsonValue) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(item, int) and not isinstance(item, bool)
    }


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    return dict(value) if isinstance(value, dict) else {}


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _session_sort_key(info: JsonValue) -> str:
    if isinstance(info, dict):
        started = info.get("started_at")
        if isinstance(started, str):
            return started
    return ""


def _logs_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / SESSION_LOGS_DIR


def _session_path(profile: ProfileState, session_id: str) -> Path:
    return _logs_dir(profile) / f"{_sanitize_session_id(session_id)}.jsonl"


def _lock_path(profile: ProfileState) -> Path:
    return _logs_dir(profile) / INGEST_LOCK_FILE
