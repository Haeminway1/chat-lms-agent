from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, cast

from chat_lms_agent.agent_tools import default_agent_tools
from chat_lms_agent.harness_context import academy_db_context
from chat_lms_agent.journal import redact_runtime_text
from chat_lms_agent.oss_references import oss_reference_context
from chat_lms_agent.side_panel import side_panel_contract_shape
from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState, load_memory

if TYPE_CHECKING:
    from pathlib import Path

OffloadKind = Literal["tool_output", "db_result", "log", "report_draft"]
OFFLOAD_KINDS: Final = ("tool_output", "db_result", "log", "report_draft")


@dataclass(frozen=True, slots=True)
class OffloadRecord:
    offload_id: str
    kind: OffloadKind
    sha256: str
    bytes_count: int
    summary: str


def build_context_map(profile: ProfileState) -> dict[str, JsonValue]:
    memory_entries = load_memory(profile)
    tool_ids: list[JsonValue] = [tool["id"] for tool in default_agent_tools()]
    memory_keys = [entry["key"] for entry in memory_entries]
    memory_values: list[JsonValue] = list(memory_keys)
    payload: dict[str, JsonValue] = {
        "status": "PASS",
        "schema_version": "context-map-v1",
        "truth_source": "generated_from_canonical_sources",
        "profile_root": "<profile-root>",
        "tool_ids": tool_ids,
        "memory_keys": memory_values,
        "side_panel": side_panel_contract_shape(),
        "academy_db": academy_db_context(profile),
        "oss_reference_registry": oss_reference_context(),
    }
    _write_json(_context_map_path(profile), payload)
    return payload


def show_context_map(profile: ProfileState) -> tuple[int, dict[str, JsonValue]]:
    payload = _read_json(_context_map_path(profile))
    if payload is None:
        return 2, {"status": "ERROR", "error_code": "CONTEXT_MAP_NOT_FOUND"}
    return 0, payload


def put_offload(
    profile: ProfileState,
    kind: str,
    source_path: Path,
) -> tuple[int, dict[str, JsonValue]]:
    parsed_kind = _parse_kind(kind)
    if parsed_kind is None:
        return 2, {"status": "ERROR", "error_code": "INVALID_OFFLOAD_KIND"}
    try:
        content = source_path.read_text(encoding="utf-8")
    except OSError:
        return 2, {"status": "ERROR", "error_code": "OFFLOAD_SOURCE_NOT_FOUND"}
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    offload_id = f"offload_{digest[:16]}"
    summary = redact_runtime_text(profile, content[:240])
    record = OffloadRecord(
        offload_id=offload_id,
        kind=parsed_kind,
        sha256=digest,
        bytes_count=len(content.encode("utf-8")),
        summary=summary,
    )
    _offload_dir(profile).mkdir(parents=True, exist_ok=True)
    _ = _offload_content_path(profile, offload_id).write_text(content, encoding="utf-8")
    _write_json(_offload_meta_path(profile, offload_id), _offload_json(record))
    return 0, {"status": "PASS", **_offload_json(record)}


def get_offload(
    profile: ProfileState,
    offload_id: str,
    *,
    reveal: bool = False,
) -> tuple[int, dict[str, JsonValue]]:
    meta = _read_json(_offload_meta_path(profile, offload_id))
    if meta is None:
        return 2, {"status": "ERROR", "error_code": "OFFLOAD_NOT_FOUND", "recoverable": True}
    content_path = _offload_content_path(profile, offload_id)
    if not content_path.exists():
        return (
            2,
            {
                "status": "ERROR",
                "error_code": "OFFLOAD_ORIGINAL_MISSING",
                "recoverable": True,
            },
        )
    content = content_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    expected = meta.get("sha256")
    visible_content = content if reveal else redact_runtime_text(profile, content)
    return (
        0,
        {
            "status": "PASS",
            "offload_id": offload_id,
            "sha256": digest,
            "integrity": "PASS" if digest == expected else "FAIL",
            "content": visible_content,
            "content_redacted": not reveal,
        },
    )


def budget_payload(profile: ProfileState) -> dict[str, JsonValue]:
    records = _offload_records(profile)
    total_bytes = sum(record.bytes_count for record in records)
    return {
        "status": "PASS",
        "schema_version": "context-budget-v1",
        "offload_count": len(records),
        "offloaded_bytes": total_bytes,
        "strategy": "summaries_in_context_originals_by_id",
    }


def _parse_kind(kind: str) -> OffloadKind | None:
    match kind:
        case "tool_output":
            return "tool_output"
        case "db_result":
            return "db_result"
        case "log":
            return "log"
        case "report_draft":
            return "report_draft"
        case _:
            return None


def _offload_records(profile: ProfileState) -> list[OffloadRecord]:
    records: list[OffloadRecord] = []
    for path in sorted(_offload_dir(profile).glob("*.json")):
        payload = _read_json(path)
        if payload is None:
            continue
        record = _parse_offload(payload)
        if record is not None:
            records.append(record)
    return records


def _parse_offload(payload: dict[str, JsonValue]) -> OffloadRecord | None:
    offload_id = payload.get("offload_id")
    kind = _parse_kind(str(payload.get("kind")))
    sha256 = payload.get("sha256")
    bytes_count = payload.get("bytes_count")
    summary = payload.get("summary")
    if not (
        isinstance(offload_id, str)
        and kind is not None
        and isinstance(sha256, str)
        and isinstance(bytes_count, int)
        and isinstance(summary, str)
    ):
        return None
    return OffloadRecord(offload_id, kind, sha256, bytes_count, summary)


def _offload_json(record: OffloadRecord) -> dict[str, JsonValue]:
    return {
        "schema_version": "context-offload-v1",
        "offload_id": record.offload_id,
        "kind": record.kind,
        "sha256": record.sha256,
        "bytes_count": record.bytes_count,
        "summary": record.summary,
    }


def _context_map_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "context-map.json"


def _offload_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "context-offload"


def _offload_meta_path(profile: ProfileState, offload_id: str) -> Path:
    return _offload_dir(profile) / f"{offload_id}.json"


def _offload_content_path(profile: ProfileState, offload_id: str) -> Path:
    return _offload_dir(profile) / f"{offload_id}.txt"


def _read_json(path: Path) -> dict[str, JsonValue] | None:
    if not path.exists():
        return None
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)
