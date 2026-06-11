from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_write_json_survives_legacy_console_codepage(tmp_path: Path) -> None:
    # Given: payload text containing a character cp949 cannot encode (em dash),
    # on a child whose stdout is pinned to the legacy Korean codepage.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    env["PYTHONIOENCODING"] = "cp949"

    # When: the CLI succeeds and echoes the payload.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chat_lms_agent",
            "memory",
            "upsert",
            "--key",
            "note:dash",
            "--scope",
            "durable",
            "--text",
            "before — after",
            "--profile-root",
            str(tmp_path),
            "--json",
        ],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        input="",
    )

    # Then: the echo degrades gracefully instead of crashing after the write.
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert '"status": "PASS"' in result.stdout


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
