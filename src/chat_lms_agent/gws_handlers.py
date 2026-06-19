"""Google Workspace CLI handler.

``setup`` runs the one-time browser consent; ``status`` reports the badge.
Calendar/Drive/Sheets writes are additive on the teacher's own account and
run directly; ``gmail send`` requires an APPROVED, unconsumed approval
because a misaddressed mail to a parent cannot be unsent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.approvals import (
    approval_id_for,
    approval_is_approved,
    approval_is_consumed,
    approval_is_denied,
    consume_approval,
    ensure_approval_request,
)
from chat_lms_agent.cli_io import (
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.gws_api import (
    calendar_create_event,
    calendar_list,
    drive_upload,
    gmail_send,
    sheets_append,
    sheets_batch_clear,
    sheets_batch_update,
    sheets_clear,
    sheets_create,
    sheets_update,
)
from chat_lms_agent.gws_auth import (
    GwsAuthError,
    default_client_path,
    default_token_path,
    load_valid_access_token,
    parse_client_json_text,
    resolve_client,
    token_status,
    write_token,
)
from chat_lms_agent.gws_setup import run_consent_flow

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

_SEND_APPROVAL_KIND = "gws_gmail_send"


def handle_gws(args: list[str], repo_root: Path) -> int:
    command = subcommand(args)
    handlers = {
        "setup": lambda: _setup(args),
        "status": lambda: _status(args),
        "client": lambda: _client(args),
        "calendar": lambda: _calendar(args),
        "drive": lambda: _drive(args),
        "sheets": lambda: _sheets(args),
        "gmail": lambda: _gmail(args, repo_root),
    }
    handler = handlers.get(command or "")
    if handler is None:
        write_json({"status": "ERROR", "error_code": "UNKNOWN_GWS_COMMAND"})
        return 2
    try:
        return handler()
    except GwsAuthError as error:
        write_json({"status": "ERROR", "error_code": error.error_code, "message": error.message})
        return 2


def _setup(args: list[str]) -> int:
    client_file = option(args, "--client-file")
    client = resolve_client(Path(client_file) if client_file else None)
    if client is None:
        write_json(
            {
                "status": "ERROR",
                "error_code": "GWS_CLIENT_MISSING",
                "message_ko": (
                    "OAuth 클라이언트가 아직 없습니다. 콘솔에서 만든 JSON을 받았다면 "
                    "chat-lms gws client install 이 다운로드 폴더에서 자동 설치합니다. "
                    "아직이라면 에이전트가 브라우저로 콘솔 절차를 대신 진행할 수 있습니다 "
                    "(사용자는 로그인만)."
                ),
            },
        )
        return 2
    token = run_consent_flow(client[0], client[1])
    token_path = _token_path(args)
    write_token(token_path, token)
    status = token_status(token_path)
    status["client_source"] = client[2]
    write_json({"status": "PASS", "gws": status})
    return 0


def _client(args: list[str]) -> int:
    if _second_verb(args) != "install":
        write_json({"status": "ERROR", "error_code": "UNKNOWN_GWS_COMMAND"})
        return 2
    downloads_raw = option(args, "--downloads")
    downloads = Path(downloads_raw) if downloads_raw else Path.home() / "Downloads"
    target_raw = option(args, "--to")
    target = Path(target_raw) if target_raw else default_client_path()
    newest = _newest_client_json(downloads)
    if newest is None:
        write_json(
            {
                "status": "ERROR",
                "error_code": "GWS_CLIENT_JSON_NOT_FOUND",
                "message_ko": (
                    f"{downloads} 에서 client_secret*.json 을 찾지 못했습니다. "
                    "Google Cloud Console에서 '데스크톱 앱' OAuth 클라이언트의 JSON을 "
                    "다운로드한 뒤 다시 실행하세요 — 콘솔 절차는 에이전트가 브라우저로 "
                    "대신 진행할 수 있습니다 (사용자는 로그인만)."
                ),
            },
        )
        return 2
    text = newest.read_text(encoding="utf-8-sig")
    parsed = parse_client_json_text(text)
    if parsed is None:
        write_json(
            {
                "status": "ERROR",
                "error_code": "GWS_CLIENT_JSON_INVALID",
                "file": str(newest),
                "message_ko": "다운로드된 JSON이 데스크톱용 OAuth 클라이언트 형식이 아닙니다.",
            },
        )
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")
    write_json(
        {
            "status": "PASS",
            "client_source": "downloads",
            "installed_to": (
                "~/.chat_lms_agent/google_client.json" if not target_raw else str(target)
            ),
            "client_id_masked": _mask_client_id(parsed[0]),
            "next_command": "python -m chat_lms_agent gws setup --json",
        },
    )
    return 0


def _status(args: list[str]) -> int:
    status = token_status(_token_path(args))
    write_json({"status": "PASS" if status.get("status") == "PASS" else "ERROR", "gws": status})
    return 0 if status.get("status") == "PASS" else 1


def _calendar(args: list[str]) -> int:
    verb = _second_verb(args)
    access = load_valid_access_token(_token_path(args))
    if verb == "list":

        result = calendar_list(
            access,
            required_option(args, "--from"),
            required_option(args, "--to"),
        )
        write_json({"status": "PASS", "events": _event_summaries(result)})
        return 0
    if verb == "create-event":

        created = calendar_create_event(
            access,
            required_option(args, "--title"),
            required_option(args, "--start"),
            required_option(args, "--end"),
            description=option(args, "--description"),
        )
        write_json(
            {"status": "PASS", "event_id": created.get("id"), "link": created.get("htmlLink")},
        )
        return 0
    write_json({"status": "ERROR", "error_code": "UNKNOWN_GWS_COMMAND"})
    return 2


def _drive(args: list[str]) -> int:
    if _second_verb(args) != "upload":
        write_json({"status": "ERROR", "error_code": "UNKNOWN_GWS_COMMAND"})
        return 2
    file_path = Path(required_option(args, "--file"))
    if not file_path.exists():
        write_json({"status": "ERROR", "error_code": "GWS_FILE_NOT_FOUND", "file": str(file_path)})
        return 2
    access = load_valid_access_token(_token_path(args))

    uploaded = drive_upload(access, file_path, folder_name=option(args, "--folder-name"))
    write_json(
        {
            "status": "PASS",
            "file_id": uploaded.get("id"),
            "link": uploaded.get("webViewLink"),
        },
    )
    return 0


def _sheets(args: list[str]) -> int:
    verb = _second_verb(args)
    access = load_valid_access_token(_token_path(args))
    if verb == "create":

        rows = _read_tsv(Path(required_option(args, "--from-tsv")))
        created = sheets_create(access, required_option(args, "--title"), rows)
        write_json(
            {
                "status": "PASS",
                "sheet_id": created.get("spreadsheetId"),
                "link": created.get("spreadsheetUrl"),
                "rows": len(rows),
            },
        )
        return 0
    if verb == "append":

        rows = _read_tsv(Path(required_option(args, "--from-tsv")))
        range_name = option(args, "--range") or "A1"
        _ = sheets_append(access, required_option(args, "--sheet-id"), rows, range_name=range_name)
        write_json({"status": "PASS", "rows": len(rows), "range": range_name})
        return 0
    if verb == "update":

        rows = _read_tsv(Path(required_option(args, "--from-tsv")))
        range_name = required_option(args, "--range")
        _ = sheets_update(access, required_option(args, "--sheet-id"), rows, range_name)
        write_json({"status": "PASS", "rows": len(rows), "range": range_name})
        return 0
    if verb == "clear":

        range_name = required_option(args, "--range")
        _ = sheets_clear(access, required_option(args, "--sheet-id"), range_name)
        write_json({"status": "PASS", "range": range_name})
        return 0
    if verb == "batch-update":

        payload = _read_json_payload(Path(required_option(args, "--from-json")))
        data = payload.get("data")
        if not isinstance(data, list):
            write_json({"status": "ERROR", "error_code": "GWS_INVALID_BATCH_PAYLOAD"})
            return 2
        result = sheets_batch_update(access, required_option(args, "--sheet-id"), data)
        write_json(
            {
                "status": "PASS",
                "ranges": len(data),
                "total_updated_cells": result.get("totalUpdatedCells"),
            },
        )
        return 0
    if verb == "batch-clear":

        payload = _read_json_payload(Path(required_option(args, "--from-json")))
        ranges = payload.get("ranges")
        if not isinstance(ranges, list) or not all(isinstance(item, str) for item in ranges):
            write_json({"status": "ERROR", "error_code": "GWS_INVALID_BATCH_PAYLOAD"})
            return 2
        result = sheets_batch_clear(access, required_option(args, "--sheet-id"), ranges)
        write_json(
            {
                "status": "PASS",
                "ranges": len(ranges),
                "cleared_ranges": result.get("clearedRanges"),
            },
        )
        return 0
    write_json({"status": "ERROR", "error_code": "UNKNOWN_GWS_COMMAND"})
    return 2


def _gmail(args: list[str], repo_root: Path) -> int:
    if _second_verb(args) != "send":
        write_json({"status": "ERROR", "error_code": "UNKNOWN_GWS_COMMAND"})
        return 2
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    to = required_option(args, "--to")
    subject = required_option(args, "--subject")
    body_path = Path(required_option(args, "--body-file"))
    # The plan id binds the approval to this exact recipient and subject:
    # approving one send never authorizes a different one.
    plan_id = f"{_SEND_APPROVAL_KIND}:{to}:{subject}"
    operation = f"gws gmail send to {to}: {subject}"
    plan_approval_id = approval_id_for(plan_id)
    approval_id = option(args, "--approval-id")
    if approval_is_denied(profile, plan_approval_id, plan_id) or approval_is_consumed(
        profile,
        plan_approval_id,
        plan_id,
    ):
        write_json(
            {
                "status": "BLOCKED",
                "error_code": "GWS_APPROVAL_UNAVAILABLE",
                "approval_id": plan_approval_id,
                "message_ko": "이 발송 건의 승인이 거부되었거나 이미 사용되었습니다.",
            },
        )
        return 5
    if approval_id is None or not approval_is_approved(profile, approval_id, plan_id):
        request = ensure_approval_request(profile, plan_id=plan_id, operation=operation)
        write_json(
            {
                "status": "NEEDS_APPROVAL",
                "approval_id": request.get("approval_id"),
                "operation": operation,
                "message_ko": (
                    "메일 발송은 교사 승인이 필요합니다. approve 후 --approval-id 로 "
                    "다시 실행하세요."
                ),
            },
        )
        return 3
    attach_raw = option(args, "--attach")
    access = load_valid_access_token(_token_path(args))

    sent = gmail_send(
        access,
        to,
        subject,
        body_path.read_text(encoding="utf-8-sig"),
        attach=Path(attach_raw) if attach_raw else None,
    )
    consume_approval(profile, approval_id, plan_id)
    write_json({"status": "PASS", "message_id": sent.get("id"), "to": to})
    return 0


def _event_summaries(result: dict[str, JsonValue]) -> list[JsonValue]:
    items = result.get("items")
    summaries: list[JsonValue] = []
    if not isinstance(items, list):
        return summaries
    for item in items:
        if not isinstance(item, dict):
            continue
        start = item.get("start")
        start_value: JsonValue = None
        if isinstance(start, dict):
            start_value = start.get("dateTime") or start.get("date")
        summaries.append({"summary": item.get("summary"), "start": start_value})
    return summaries


def _read_tsv(tsv_path: Path) -> list[list[str]]:
    text = tsv_path.read_text(encoding="utf-8-sig")
    return [line.split("\t") for line in text.splitlines() if line.strip()]


def _read_json_payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        return payload
    return {}


def _token_path(args: list[str]) -> Path:
    override = option(args, "--token-file")
    return Path(override) if override else default_token_path()


def _newest_client_json(downloads: Path) -> Path | None:
    try:
        candidates = sorted(
            downloads.glob("client_secret*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    return candidates[0] if candidates else None


def _mask_client_id(client_id: str) -> str:
    visible = 6
    head, _, tail = client_id.partition(".")
    masked_head = f"{head[:visible]}…" if len(head) > visible else head
    return f"{masked_head}.{tail}" if tail else masked_head


def _second_verb(args: list[str]) -> str | None:
    rest = args[2:] if len(args) > 2 else []  # noqa: PLR2004 - chat-lms gws <verb> <subverb>
    for token in rest:
        if not token.startswith("-"):
            return token
    return None
