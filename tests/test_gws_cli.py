"""gws CLI contract tests — no network, synthetic token files only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent import gws_api, gws_handlers
from chat_lms_agent.approvals import approve_request, pending_approval_ids
from chat_lms_agent.gws_auth import GWS_SCOPES
from chat_lms_agent.state import ProfileState, resolve_profile_state

if TYPE_CHECKING:
    import pytest


def _seed_token(token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    _ = token_path.write_text(
        json.dumps(
            {
                "client_id": "client-1",
                "client_secret": "secret-1",
                "token_uri": "https://oauth2.googleapis.com/token",
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "scopes": GWS_SCOPES,
                "expires_at": time.time() + 3600,
            },
        ),
        encoding="utf-8",
    )


def test_status_without_token_reports_needs_setup(tmp_path: Path) -> None:
    result = _run_cli("gws", "status", "--token-file", str(tmp_path / "t.json"), "--json")

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["gws"]["error_code"] == "GWS_TOKEN_MISSING"


def test_setup_without_client_names_the_owner_step(tmp_path: Path) -> None:
    result = _run_cli(
        "gws",
        "setup",
        "--client-file",
        str(tmp_path / "missing-client.json"),
        "--token-file",
        str(tmp_path / "t.json"),
        "--json",
    )

    assert result.returncode == 2, result.stdout
    assert json.loads(result.stdout)["error_code"] == "GWS_CLIENT_MISSING"


def test_calendar_without_token_fails_typed_not_traceback(tmp_path: Path) -> None:
    result = _run_cli(
        "gws",
        "calendar",
        "list",
        "--from",
        "2026-06-08T00:00:00+09:00",
        "--to",
        "2026-06-14T00:00:00+09:00",
        "--token-file",
        str(tmp_path / "absent.json"),
        "--json",
    )

    assert result.returncode == 2, result.stdout
    assert "Traceback" not in result.stderr
    assert json.loads(result.stdout)["error_code"] == "GWS_TOKEN_MISSING"


def test_gmail_send_demands_approval_before_any_network(tmp_path: Path) -> None:
    # Given: a valid token; the approval ledger is empty.
    token_path = tmp_path / "t.json"
    _seed_token(token_path)
    body = tmp_path / "body.txt"
    _ = body.write_text("시험지 보내드립니다.", encoding="utf-8")

    # When: send runs without --approval-id (transport never invoked: the
    # gate sits before any token/network use).
    result = _run_cli(
        "gws",
        "gmail",
        "send",
        "--to",
        "parent@example.com",
        "--subject",
        "6월 시험지",
        "--body-file",
        str(body),
        "--token-file",
        str(token_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: NEEDS_APPROVAL with a stable approval id.
    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "NEEDS_APPROVAL"
    assert payload["approval_id"]
    assert "parent@example.com" in payload["operation"]


def test_gmail_send_with_approval_sends_and_consumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a planned approval that the teacher then approves.
    token_path = tmp_path / "t.json"
    _seed_token(token_path)
    body = tmp_path / "body.txt"
    _ = body.write_text("시험지 보내드립니다.", encoding="utf-8")
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    args = [
        "gws",
        "gmail",
        "send",
        "--to",
        "parent@example.com",
        "--subject",
        "6월 시험지",
        "--body-file",
        str(body),
        "--token-file",
        str(token_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    ]
    first = gws_handlers.handle_gws(args, _repo_root())
    assert first == 3
    approval_id = _planned_approval_id(profile)
    _ = approve_request(profile, approval_id, "teacher")

    # When: the send runs with the approval, transport faked at the API edge.
    sent_bodies: list[bytes | None] = []

    def fake_transport(
        method: str,
        url: str,
        headers: dict[str, str],
        request_body: bytes | None,
    ) -> bytes:
        _ = (method, url, headers)
        sent_bodies.append(request_body)
        return b'{"id": "msg-1"}'

    monkeypatch.setattr(gws_api, "_default_transport", fake_transport)
    second = gws_handlers.handle_gws([*args, "--approval-id", approval_id], _repo_root())

    # Then: the mail went out exactly once and the approval is consumed.
    assert second == 0
    assert len(sent_bodies) == 1
    third = gws_handlers.handle_gws([*args, "--approval-id", approval_id], _repo_root())
    assert third == 5


def _planned_approval_id(profile: ProfileState) -> str:
    ids = pending_approval_ids(profile)
    assert ids
    return ids[0]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        input="",
    )
