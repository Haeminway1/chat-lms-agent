from __future__ import annotations

import base64
import json
from email import message_from_bytes
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.gws_api import (
    calendar_create_event,
    calendar_list,
    drive_upload,
    gmail_send,
    sheets_create,
)


class _FakeTransport:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> bytes:
        self.calls.append((method, url, headers, body))
        return json.dumps(self.responses[len(self.calls) - 1]).encode("utf-8")


def test_calendar_list_sends_bearer_and_window() -> None:
    transport = _FakeTransport([{"items": []}])

    result = calendar_list(
        "access-1",
        "2026-06-08T00:00:00+09:00",
        "2026-06-14T23:59:59+09:00",
        transport,
    )

    assert result == {"items": []}
    method, url, headers, body = transport.calls[0]
    assert method == "GET"
    assert url.startswith("https://www.googleapis.com/calendar/v3/calendars/primary/events?")
    assert "timeMin=2026-06-08" in url
    assert headers["Authorization"] == "Bearer access-1"
    assert body is None


def test_calendar_create_event_builds_datetime_body() -> None:
    transport = _FakeTransport([{"id": "evt-1"}])

    _ = calendar_create_event(
        "access-1",
        "수학 수업",
        "2026-06-12T16:00:00",
        "2026-06-12T17:00:00",
        description="기말 대비",
        transport=transport,
    )

    method, _url, _headers, body = transport.calls[0]
    assert method == "POST"
    assert body is not None
    payload = json.loads(body.decode("utf-8"))
    assert payload["summary"] == "수학 수업"
    assert payload["start"] == {"dateTime": "2026-06-12T16:00:00", "timeZone": "Asia/Seoul"}
    assert payload["description"] == "기말 대비"


def test_drive_upload_into_named_folder_reuses_existing_folder(tmp_path: Path) -> None:
    artifact = tmp_path / "단어시험지.txt"
    _ = artifact.write_text("apple\t사과\n", encoding="utf-8")
    transport = _FakeTransport(
        [
            {"files": [{"id": "folder-9", "name": "시험지"}]},
            {"id": "file-1", "webViewLink": "https://drive.google.com/x"},
        ],
    )

    result = drive_upload("access-1", artifact, folder_name="시험지", transport=transport)

    assert result["id"] == "file-1"
    search_method, search_url, _h, _b = transport.calls[0]
    assert search_method == "GET"
    assert "mimeType+%3D+%27application%2Fvnd.google-apps.folder%27" in search_url
    upload_method, upload_url, upload_headers, upload_body = transport.calls[1]
    assert upload_method == "POST"
    assert "uploadType=multipart" in upload_url
    assert upload_headers["Content-Type"].startswith("multipart/related; boundary=")
    assert upload_body is not None
    assert b'"parents": ["folder-9"]' in upload_body
    assert "apple\t사과".encode() in upload_body


def test_sheets_create_appends_rows_after_creation() -> None:
    transport = _FakeTransport([{"spreadsheetId": "sheet-1"}, {"updates": {}}])

    result = sheets_create(
        "access-1",
        "6월 단어시험",
        [["apple", "사과"], ["river", "강"]],
        transport,
    )

    assert result["spreadsheetId"] == "sheet-1"
    _m, create_url, _h, create_body = transport.calls[0]
    assert create_url == "https://sheets.googleapis.com/v4/spreadsheets"
    assert create_body is not None
    assert json.loads(create_body)["properties"]["title"] == "6월 단어시험"
    _m2, append_url, _h2, append_body = transport.calls[1]
    assert "/values/A1:append?valueInputOption=RAW" in append_url
    assert append_body is not None
    assert json.loads(append_body)["values"] == [["apple", "사과"], ["river", "강"]]


def test_gmail_send_encodes_mime_with_attachment(tmp_path: Path) -> None:
    attachment = tmp_path / "시험지.txt"
    _ = attachment.write_text("apple\t사과\n", encoding="utf-8")
    transport = _FakeTransport([{"id": "msg-1"}])

    _ = gmail_send(
        "access-1",
        "parent@example.com",
        "6월 단어시험지",
        "안녕하세요, 시험지 보내드립니다.",
        attach=attachment,
        transport=transport,
    )

    _m, url, _h, body = transport.calls[0]
    assert url == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    assert body is not None
    raw = json.loads(body.decode("utf-8"))["raw"]
    mime = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert mime["To"] == "parent@example.com"
    assert "단어시험지" in str(mime["Subject"]) or "=?utf-8?" in str(mime["Subject"])
    attachment_names = [part.get_filename() for part in mime.walk() if part.get_filename()]
    assert attachment_names == ["시험지.txt"]
