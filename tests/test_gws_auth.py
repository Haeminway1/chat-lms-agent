from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

import pytest

from chat_lms_agent.gws_auth import (
    GWS_SCOPES,
    GwsAuthError,
    load_valid_access_token,
    token_status,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_token(
    path: Path,
    *,
    scopes: list[str] | None = None,
    expires_at: float | None = None,
    refresh_token: str | None = None,
) -> None:
    payload = {
        "client_id": "client-1",
        "client_secret": "secret-1",
        "token_uri": "https://oauth2.googleapis.com/token",
        "access_token": "access-old",
        "refresh_token": "refresh-1" if refresh_token is None else refresh_token,
        "scopes": GWS_SCOPES if scopes is None else scopes,
        "expires_at": time.time() + 3600 if expires_at is None else expires_at,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding="utf-8")


def test_status_without_token_is_needs_setup(tmp_path: Path) -> None:
    status = token_status(tmp_path / "google_token.json")
    assert status["status"] == "NEEDS_SETUP"


def test_status_with_valid_token_masks_material(tmp_path: Path) -> None:
    token_path = tmp_path / "google_token.json"
    _write_token(token_path)

    status = token_status(token_path)

    assert status["status"] == "PASS"
    assert status["scopes"] == GWS_SCOPES
    blob = json.dumps(status)
    assert "access-old" not in blob
    assert "refresh-1" not in blob
    assert "secret-1" not in blob


def test_status_with_missing_scope_demands_resetup(tmp_path: Path) -> None:
    token_path = tmp_path / "google_token.json"
    _write_token(token_path, scopes=[GWS_SCOPES[0]])

    status = token_status(token_path)

    assert status["status"] == "NEEDS_SETUP"
    assert status["error_code"] == "GWS_SCOPES_MISSING"


def test_expired_token_refreshes_through_injected_transport(tmp_path: Path) -> None:
    token_path = tmp_path / "google_token.json"
    _write_token(token_path, expires_at=time.time() - 10)
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_transport(url: str, data: dict[str, str], headers: dict[str, str]) -> bytes:
        _ = headers
        calls.append((url, data))
        return json.dumps({"access_token": "access-new", "expires_in": 3599}).encode("utf-8")

    access = load_valid_access_token(token_path, transport=fake_transport)

    assert access == "access-new"
    assert calls[0][0] == "https://oauth2.googleapis.com/token"
    assert calls[0][1]["grant_type"] == "refresh_token"
    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["access_token"] == "access-new"
    assert saved["expires_at"] > time.time()


def test_refresh_without_refresh_token_raises_typed_error(tmp_path: Path) -> None:
    token_path = tmp_path / "google_token.json"
    _write_token(token_path, expires_at=time.time() - 10, refresh_token="")

    with pytest.raises(GwsAuthError) as exc_info:
        _ = load_valid_access_token(token_path, transport=lambda *_args: b"{}")
    assert exc_info.value.error_code == "GWS_TOKEN_INVALID"
