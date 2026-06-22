"""Google Workspace REST calls — standard library only.

Calendar events, Sheets, Drive (``drive.file`` scope: only files this app
created), and Gmail send, each as a plain HTTPS request with a Bearer
token. A transport callable is injected by tests so CI never talks to
Google.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.gws_auth import GwsAuthError

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPResponse
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

type ApiTransport = Callable[[str, str, dict[str, str], bytes | None], bytes]
"""(method, url, headers, body) -> response body bytes."""

CALENDAR_EVENTS_URL: Final = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
DRIVE_FILES_URL: Final = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL: Final = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
SHEETS_URL: Final = "https://sheets.googleapis.com/v4/spreadsheets"
GMAIL_SEND_URL: Final = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
DEFAULT_TIMEZONE: Final = "Asia/Seoul"
_MULTIPART_BOUNDARY: Final = "chat-lms-gws-boundary-7f3d2a"
_HTTP_UNAUTHORIZED: Final = 401


def _api_error(error_code: str, message: str) -> GwsAuthError:
    return GwsAuthError(error_code, message)


def calendar_list(
    access_token: str,
    time_min: str,
    time_max: str,
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    query = urllib.parse.urlencode(
        {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
        },
    )
    return _json_request(access_token, "GET", f"{CALENDAR_EVENTS_URL}?{query}", None, transport)


def calendar_create_event(  # noqa: PLR0913 - explicit API surface
    access_token: str,
    title: str,
    start: str,
    end: str,
    description: str | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    body: dict[str, JsonValue] = {
        "summary": title,
        "start": _event_time(start, timezone),
        "end": _event_time(end, timezone),
    }
    if description is not None:
        body["description"] = description
    return _json_request(access_token, "POST", CALENDAR_EVENTS_URL, body, transport)


def drive_upload(
    access_token: str,
    file_path: Path,
    folder_name: str | None = None,
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {"name": file_path.name}
    if folder_name is not None:
        folder_id = _ensure_folder(access_token, folder_name, transport)
        parents: list[JsonValue] = [folder_id]
        metadata["parents"] = parents
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    boundary = _MULTIPART_BOUNDARY
    body = b"".join(
        (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
            json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
            f"\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            f"\r\n--{boundary}--".encode(),
        ),
    )
    headers = {"Content-Type": f"multipart/related; boundary={boundary}"}
    raw = _request(
        access_token,
        "POST",
        f"{DRIVE_UPLOAD_URL}&fields=id,name,webViewLink",
        headers,
        body,
        transport,
    )
    return _parse_object(raw)


def sheets_create(
    access_token: str,
    title: str,
    rows: list[list[str]],
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    created = _json_request(
        access_token,
        "POST",
        SHEETS_URL,
        {"properties": {"title": title}},
        transport,
    )
    sheet_id = created.get("spreadsheetId")
    if isinstance(sheet_id, str) and rows:
        _ = sheets_append(access_token, sheet_id, rows, transport)
    return created


def sheets_append(
    access_token: str,
    sheet_id: str,
    rows: list[list[str]],
    transport: ApiTransport | None = None,
    range_name: str = "A1",
) -> dict[str, JsonValue]:
    values: list[JsonValue] = [cast("JsonValue", list(row)) for row in rows]
    encoded_range = urllib.parse.quote(range_name, safe="")
    url = (
        f"{SHEETS_URL}/{urllib.parse.quote(sheet_id)}/values/{encoded_range}:append"
        "?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    return _json_request(access_token, "POST", url, {"values": values}, transport)


def sheets_update(
    access_token: str,
    sheet_id: str,
    rows: list[list[str]],
    range_name: str,
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    values: list[JsonValue] = [cast("JsonValue", list(row)) for row in rows]
    encoded_range = urllib.parse.quote(range_name, safe="")
    url = (
        f"{SHEETS_URL}/{urllib.parse.quote(sheet_id)}/values/{encoded_range}"
        "?valueInputOption=RAW"
    )
    return _json_request(access_token, "PUT", url, {"values": values}, transport)


def sheets_values_get(
    access_token: str,
    sheet_id: str,
    range_name: str,
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    encoded_range = urllib.parse.quote(range_name, safe="")
    url = (
        f"{SHEETS_URL}/{urllib.parse.quote(sheet_id)}/values/{encoded_range}"
        "?majorDimension=ROWS"
    )
    return _json_request(access_token, "GET", url, None, transport)


def sheets_clear(
    access_token: str,
    sheet_id: str,
    range_name: str,
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    encoded_range = urllib.parse.quote(range_name, safe="")
    url = f"{SHEETS_URL}/{urllib.parse.quote(sheet_id)}/values/{encoded_range}:clear"
    return _json_request(access_token, "POST", url, {}, transport)


def sheets_batch_update(
    access_token: str,
    sheet_id: str,
    updates: list[dict[str, JsonValue]],
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    data: list[JsonValue] = cast("list[JsonValue]", updates)
    url = f"{SHEETS_URL}/{urllib.parse.quote(sheet_id)}/values:batchUpdate"
    return _json_request(
        access_token,
        "POST",
        url,
        {"valueInputOption": "RAW", "data": data},
        transport,
    )


def sheets_batch_clear(
    access_token: str,
    sheet_id: str,
    ranges: list[str],
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    url = f"{SHEETS_URL}/{urllib.parse.quote(sheet_id)}/values:batchClear"
    return _json_request(
        access_token,
        "POST",
        url,
        {"ranges": cast("JsonValue", ranges)},
        transport,
    )


def gmail_send(  # noqa: PLR0913 - explicit API surface
    access_token: str,
    to: str,
    subject: str,
    body_text: str,
    attach: Path | None = None,
    transport: ApiTransport | None = None,
) -> dict[str, JsonValue]:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body_text)
    if attach is not None:
        content_type = mimetypes.guess_type(attach.name)[0] or "application/octet-stream"
        maintype, _, subtype = content_type.partition("/")
        message.add_attachment(
            attach.read_bytes(),
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=attach.name,
        )
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return _json_request(access_token, "POST", GMAIL_SEND_URL, {"raw": raw}, transport)


def _ensure_folder(
    access_token: str,
    folder_name: str,
    transport: ApiTransport | None,
) -> str:
    safe_name = folder_name.replace("'", "\\'")
    query = urllib.parse.urlencode(
        {
            "q": (
                f"name = '{safe_name}' and "
                "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            ),
            "fields": "files(id,name)",
        },
    )
    found = _json_request(access_token, "GET", f"{DRIVE_FILES_URL}?{query}", None, transport)
    files = found.get("files")
    if isinstance(files, list) and files:
        first = files[0]
        if isinstance(first, dict):
            folder_id = first.get("id")
            if isinstance(folder_id, str):
                return folder_id
    created = _json_request(
        access_token,
        "POST",
        DRIVE_FILES_URL,
        {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
        transport,
    )
    folder_id = created.get("id")
    if not isinstance(folder_id, str):
        raise _api_error(error_code="GWS_API_ERROR", message="folder creation returned no id")
    return folder_id


def _event_time(value: str, timezone: str) -> dict[str, JsonValue]:
    if "T" in value:
        return {"dateTime": value, "timeZone": timezone}
    return {"date": value}


def _json_request(
    access_token: str,
    method: str,
    url: str,
    body: dict[str, JsonValue] | None,
    transport: ApiTransport | None,
) -> dict[str, JsonValue]:
    headers = {"Content-Type": "application/json; charset=UTF-8"}
    encoded = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    raw = _request(access_token, method, url, headers, encoded, transport)
    return _parse_object(raw)


def _request(  # noqa: PLR0913 - one Bearer request pipeline
    access_token: str,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    transport: ApiTransport | None,
) -> bytes:
    request_headers = {"Authorization": f"Bearer {access_token}", **headers}
    sender = transport or _default_transport
    try:
        return sender(method, url, request_headers, body)
    except urllib.error.HTTPError as error:
        status = error.code
        snippet = error.read()[:200].decode("utf-8", errors="replace")
        code = "GWS_AUTH_EXPIRED" if status == _HTTP_UNAUTHORIZED else "GWS_API_ERROR"
        raise _api_error(error_code=code, message=f"HTTP {status}: {snippet}") from error


def _default_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> bytes:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310 - fixed https endpoints
    opened = cast("HTTPResponse", urllib.request.urlopen(request, timeout=60))  # noqa: S310
    with opened as response:
        return response.read()


def _parse_object(raw: bytes) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(raw.decode("utf-8")))
    if not isinstance(payload, dict):
        raise _api_error(error_code="GWS_API_ERROR", message="API returned a non-object response")
    return payload
