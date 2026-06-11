"""Client resolution and the zero-touch client install path.

The Toss-style contract: end users only ever see the Google consent
screen. The embedded repo default makes the client JSON unnecessary for
them; ``gws client install`` automates the owner's one-time path by
finding the freshest downloaded client JSON and installing it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from chat_lms_agent.gws_auth import resolve_client


def _client_json(client_id: str = "id-1.apps.googleusercontent.com") -> str:
    return json.dumps(
        {"installed": {"client_id": client_id, "client_secret": "cs-1"}},
        ensure_ascii=False,
    )


def test_resolve_client_prefers_explicit_then_home_then_embedded(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.json"
    _ = explicit.write_text(_client_json("explicit.apps.googleusercontent.com"), encoding="utf-8")
    home_file = tmp_path / "home-client.json"
    _ = home_file.write_text(_client_json("home.apps.googleusercontent.com"), encoding="utf-8")

    explicit_result = resolve_client(explicit, home_path=home_file)
    assert explicit_result is not None
    assert explicit_result[0].startswith("explicit.")
    assert explicit_result[2] == "explicit_file"

    home_result = resolve_client(None, home_path=home_file)
    assert home_result is not None
    assert home_result[0].startswith("home.")
    assert home_result[2] == "home_file"

    # With no files, the embedded product client carries the Toss-style
    # default: end users never need a client JSON at all.
    embedded = resolve_client(None, home_path=tmp_path / "absent.json")
    assert embedded is not None
    assert embedded[0].endswith(".apps.googleusercontent.com")
    assert embedded[2] == "embedded_default"

    # An explicit override never silently falls back to another client.
    assert resolve_client(tmp_path / "missing.json", home_path=home_file) is None


def test_client_install_picks_newest_downloaded_client_json(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    old = downloads / "client_secret_old.apps.googleusercontent.com.json"
    _ = old.write_text(_client_json("old.apps.googleusercontent.com"), encoding="utf-8")
    os.utime(old, (time.time() - 600, time.time() - 600))
    new = downloads / "client_secret_new.apps.googleusercontent.com.json"
    _ = new.write_text(_client_json("new.apps.googleusercontent.com"), encoding="utf-8")
    target = tmp_path / "installed" / "google_client.json"

    result = _run_cli(
        "gws",
        "client",
        "install",
        "--downloads",
        str(downloads),
        "--to",
        str(target),
        "--json",
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["client_source"] == "downloads"
    installed = json.loads(target.read_text(encoding="utf-8"))
    assert installed["installed"]["client_id"].startswith("new.")
    # The full secret never appears in the echo.
    assert "cs-1" not in result.stdout


def test_client_install_without_download_names_the_assisted_path(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()

    result = _run_cli(
        "gws",
        "client",
        "install",
        "--downloads",
        str(downloads),
        "--to",
        str(tmp_path / "google_client.json"),
        "--json",
    )

    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "GWS_CLIENT_JSON_NOT_FOUND"
    assert "브라우저" in payload["message_ko"]


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
