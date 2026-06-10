"""Consent-gated harness self-QA ledger.

Structural reference: oh-my-pi ``tools/report-tool-issue.ts`` and
``docs/install-id.md`` — a local-first anomaly ledger whose schema
structurally excludes learner data (fixed keyword-only fields), gated by a
one-time teacher consent, bounded by rotation, with a race-safe
exclusive-create install id. No remote endpoint exists.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, cast

from chat_lms_agent.state import (
    STATE_DIR,
    read_state_mapping,
    redact_text,
    write_state_mapping,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

QA_CONSENT_FILE: Final = "qa-consent.json"
QA_LEDGER_FILE: Final = "qa-ledger.jsonl"
INSTALL_ID_FILE: Final = "install-id"
QA_LEDGER_MAX_BYTES: Final = 262_144
QA_SUMMARY_MAX_CHARS: Final = 240

type ConsentState = Literal["unset", "granted", "denied"]


def qa_consent(profile: ProfileState) -> ConsentState:
    state = read_state_mapping(profile, QA_CONSENT_FILE).get("state")
    if state == "granted":
        return "granted"
    if state == "denied":
        return "denied"
    return "unset"


def set_qa_consent(profile: ProfileState, state: ConsentState) -> dict[str, JsonValue]:
    write_state_mapping(profile, QA_CONSENT_FILE, {"state": state})
    return {"status": "PASS", "consent": state}


def append_qa_record(
    profile: ProfileState,
    record_kind: str,
    *,
    error_code: str | None = None,
    summary: str = "",
    session_id: str | None = None,
) -> bool:
    """Append one anomaly record. Fixed fields only — learner data cannot ride."""
    if qa_consent(profile) != "granted":
        return False
    record: dict[str, JsonValue] = {
        "record_kind": record_kind,
        "error_code": error_code,
        "summary": redact_text(summary)[:QA_SUMMARY_MAX_CHARS],
        "tool_name": None,
        "session_id": session_id,
        "created_at": time.time(),
    }
    path = _ledger_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(line)
    _rotate_if_needed(path)
    return True


def list_qa_records(profile: ProfileState) -> dict[str, JsonValue]:
    path = _ledger_path(profile)
    records: list[JsonValue] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = cast("JsonValue", json.loads(line))
            except JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return {
        "status": "PASS",
        "schema_version": "qa-ledger-v1",
        "consent": qa_consent(profile),
        "records": records,
    }


def clear_qa_records(profile: ProfileState) -> dict[str, JsonValue]:
    path = _ledger_path(profile)
    removed = 0
    if path.exists():
        removed = len(path.read_text(encoding="utf-8").splitlines())
        path.unlink()
    return {"status": "PASS", "cleared": removed}


def install_id(profile: ProfileState) -> str:
    """Per-install id created with exclusive-create semantics (race safe)."""
    path = profile.root / STATE_DIR / INSTALL_ID_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip()
    new_id = uuid.uuid4().hex
    try:
        _ = os.write(descriptor, new_id.encode("utf-8"))
    finally:
        os.close(descriptor)
    return new_id


def _rotate_if_needed(path: Path) -> None:
    if path.stat().st_size <= QA_LEDGER_MAX_BYTES:
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = lines[len(lines) // 2 :]
    tmp_path = path.with_suffix(".jsonl.tmp")
    _ = tmp_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    _ = tmp_path.replace(path)


def _ledger_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / QA_LEDGER_FILE
