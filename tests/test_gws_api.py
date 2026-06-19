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
    sheets_append,
    sheets_batch_clear,
    sheets_batch_update,
    sheets_clear,
    sheets_create,
    sheets_update,
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


def test_sheets_append_accepts_explicit_range() -> None:
    transport = _FakeTransport([{"updates": {}}])

    _ = sheets_append(
        "access-1",
        "sheet-1",
        [["ok"]],
        transport=transport,
        range_name="'June 2026'!A1",
    )

    _m, append_url, _h, append_body = transport.calls[0]
    assert "/values/%27June%202026%27%21A1:append" in append_url
    assert append_body is not None
    assert json.loads(append_body)["values"] == [["ok"]]


def test_sheets_update_writes_explicit_range() -> None:
    transport = _FakeTransport([{"updatedRows": 1}])

    _ = sheets_update("access-1", "sheet-1", [["A+"]], "'19'!I7", transport)

    method, update_url, _h, update_body = transport.calls[0]
    assert method == "PUT"
    assert "/values/%2719%27%21I7?valueInputOption=RAW" in update_url
    assert update_body is not None
    assert json.loads(update_body)["values"] == [["A+"]]


def test_sheets_clear_clears_explicit_range() -> None:
    transport = _FakeTransport([{"clearedRange": "'19'!J22"}])

    _ = sheets_clear("access-1", "sheet-1", "'19'!J22", transport)

    method, clear_url, _h, clear_body = transport.calls[0]
    assert method == "POST"
    assert "/values/%2719%27%21J22:clear" in clear_url
    assert clear_body is not None
    assert json.loads(clear_body) == {}


def test_sheets_batch_update_writes_multiple_ranges() -> None:
    transport = _FakeTransport([{"totalUpdatedCells": 2}])

    _ = sheets_batch_update(
        "access-1",
        "sheet-1",
        [
            {"range": "'19'!I7", "values": [["D"]]},
            {"range": "'19'!I8", "values": [["A+"]]},
        ],
        transport,
    )

    method, update_url, _h, update_body = transport.calls[0]
    assert method == "POST"
    assert update_url.endswith("/values:batchUpdate")
    assert update_body is not None
    payload = json.loads(update_body)
    assert payload["valueInputOption"] == "RAW"
    assert payload["data"][0]["range"] == "'19'!I7"


def test_sheets_batch_clear_clears_multiple_ranges() -> None:
    transport = _FakeTransport([{"clearedRanges": ["'12'!J22"]}])

    _ = sheets_batch_clear("access-1", "sheet-1", ["'12'!J22"], transport)

    method, clear_url, _h, clear_body = transport.calls[0]
    assert method == "POST"
    assert clear_url.endswith("/values:batchClear")
    assert clear_body is not None
    assert json.loads(clear_body)["ranges"] == ["'12'!J22"]


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
