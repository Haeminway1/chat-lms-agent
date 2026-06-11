"""Google Workspace OAuth token management — standard library only.

Structural reference: the hermes-agent google-workspace skill's token
bridge. Token refresh is a plain POST to the token endpoint and the
Workspace APIs are REST, so no Google SDK is required; the core harness
stays dependency-free. The token lives in the teacher's home drawer
(``~/.chat_lms_agent/google_token.json``) — never in the repo, never in
hydration context, never in journals.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.client import HTTPResponse

    from chat_lms_agent.state import JsonValue

# Least-privilege scope set — fixed by plans/gws-integration-plan.md.
# Requesting anything beyond these four is a failure condition.
GWS_SCOPES: Final[list[str]] = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
]
TOKEN_URI: Final = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint URL, not a secret
AUTH_URI: Final = "https://accounts.google.com/o/oauth2/v2/auth"
_EXPIRY_MARGIN_SECONDS: Final = 60

type Transport = Callable[[str, dict[str, str], dict[str, str]], bytes]
"""POST form ``data`` to ``url`` with ``headers``; return the response body."""


@dataclass(frozen=True, slots=True)
class GwsAuthError(Exception):
    error_code: str
    message: str


def _auth_error(error_code: str, message: str) -> GwsAuthError:
    return GwsAuthError(error_code, message)


def default_token_path() -> Path:
    return Path.home() / ".chat_lms_agent" / "google_token.json"


def default_client_path() -> Path:
    return Path.home() / ".chat_lms_agent" / "google_client.json"


def token_status(token_path: Path) -> dict[str, JsonValue]:
    token = _read_token(token_path)
    if token is None:
        return {
            "status": "NEEDS_SETUP",
            "error_code": "GWS_TOKEN_MISSING",
            "message_ko": "Google Workspace 토큰이 없습니다. chat-lms gws setup 을 실행하세요.",
        }
    scopes = token.get("scopes")
    granted = (
        [scope for scope in scopes if isinstance(scope, str)]
        if isinstance(scopes, list)
        else []
    )
    missing = [scope for scope in GWS_SCOPES if scope not in granted]
    if missing:
        missing_values: list[JsonValue] = []
        missing_values.extend(missing)
        return {
            "status": "NEEDS_SETUP",
            "error_code": "GWS_SCOPES_MISSING",
            "missing_scopes": missing_values,
            "message_ko": "권한 범위가 부족합니다. chat-lms gws setup 을 다시 실행하세요.",
        }
    expires_at = token.get("expires_at")
    expired = not isinstance(expires_at, (int, float)) or expires_at <= time.time()
    scope_values: list[JsonValue] = []
    scope_values.extend(granted)
    return {
        "status": "PASS",
        "scopes": scope_values,
        "expired": expired,
        "refreshable": _non_empty(token.get("refresh_token")),
        "token_path": "~/.chat_lms_agent/google_token.json",
    }


def load_valid_access_token(token_path: Path, transport: Transport | None = None) -> str:
    """Return a non-expired access token, refreshing through ``transport``."""
    token = _read_token(token_path)
    if token is None:
        raise _auth_error(error_code="GWS_TOKEN_MISSING", message="run: chat-lms gws setup")
    expires_at = token.get("expires_at")
    access_token = token.get("access_token")
    if (
        isinstance(access_token, str)
        and access_token
        and isinstance(expires_at, (int, float))
        and expires_at > time.time()
    ):
        return access_token
    refreshed = _refresh(token, transport or _default_transport)
    token.update(refreshed)
    _write_token(token_path, token)
    new_access = token.get("access_token")
    if not isinstance(new_access, str) or not new_access:
        raise _auth_error(
            error_code="GWS_TOKEN_INVALID",
            message="refresh returned no access token",
        )
    return new_access


def exchange_code_for_token(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    transport: Transport | None = None,
) -> dict[str, JsonValue]:
    body = _post_form(
        TOKEN_URI,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        transport or _default_transport,
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "token_uri": TOKEN_URI,
        "access_token": body.get("access_token"),
        "refresh_token": body.get("refresh_token"),
        "scopes": _split_scopes(body.get("scope")),
        "expires_at": time.time() + _expires_in(body) - _EXPIRY_MARGIN_SECONDS,
    }


def consent_url(client_id: str, redirect_uri: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(GWS_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        },
    )
    return f"{AUTH_URI}?{query}"


def write_token(token_path: Path, token: dict[str, JsonValue]) -> None:
    _write_token(token_path, token)


def _refresh(token: dict[str, JsonValue], transport: Transport) -> dict[str, JsonValue]:
    required = ("client_id", "client_secret", "refresh_token", "token_uri")
    missing = [key for key in required if not _non_empty(token.get(key))]
    if missing:
        raise _auth_error(
            error_code="GWS_TOKEN_INVALID",
            message=f"token file is missing {', '.join(missing)}; run: chat-lms gws setup",
        )
    body = _post_form(
        str(token["token_uri"]),
        {
            "grant_type": "refresh_token",
            "client_id": str(token["client_id"]),
            "client_secret": str(token["client_secret"]),
            "refresh_token": str(token["refresh_token"]),
        },
        transport,
    )
    access_token = body.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise _auth_error(
            error_code="GWS_AUTH_EXPIRED",
            message="token refresh was rejected; run: chat-lms gws setup",
        )
    return {
        "access_token": access_token,
        "expires_at": time.time() + _expires_in(body) - _EXPIRY_MARGIN_SECONDS,
    }


def _post_form(url: str, data: dict[str, str], transport: Transport) -> dict[str, JsonValue]:
    raw = transport(url, data, {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        payload = cast("JsonValue", json.loads(raw.decode("utf-8")))
    except (JSONDecodeError, UnicodeDecodeError) as error:
        raise _auth_error(
            error_code="GWS_AUTH_PROTOCOL",
            message="token endpoint returned non-JSON",
        ) from error
    if not isinstance(payload, dict):
        raise _auth_error(
            error_code="GWS_AUTH_PROTOCOL",
            message="token endpoint returned non-object",
        )
    return payload


def _default_transport(url: str, data: dict[str, str], headers: dict[str, str]) -> bytes:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")  # noqa: S310 - fixed https endpoints
    opened = cast("HTTPResponse", urllib.request.urlopen(request, timeout=30))  # noqa: S310
    with opened as response:
        return response.read()


def _read_token(token_path: Path) -> dict[str, JsonValue] | None:
    try:
        payload = cast("JsonValue", json.loads(token_path.read_text(encoding="utf-8-sig")))
    except (OSError, JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _write_token(token_path: Path, token: dict[str, JsonValue]) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = token_path.with_suffix(".json.tmp")
    _ = tmp_path.write_text(
        json.dumps(token, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(token_path)


def _expires_in(body: dict[str, JsonValue]) -> float:
    value = body.get("expires_in")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 3600.0


def _split_scopes(value: JsonValue | None) -> list[JsonValue]:
    if not isinstance(value, str):
        scopes: list[JsonValue] = []
        scopes.extend(GWS_SCOPES)
        return scopes
    parts: list[JsonValue] = []
    parts.extend(part for part in value.split() if part)
    return parts


def _non_empty(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
