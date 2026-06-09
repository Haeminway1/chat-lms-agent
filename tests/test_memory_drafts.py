from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_memory_draft_for_tool_change_is_reviewable(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.json"

    draft_result = _run_cli(
        "memory",
        "draft",
        "--profile-root",
        str(tmp_path),
        "--for",
        "tool-change",
        "--out",
        str(draft_path),
        "--json",
    )
    list_result = _run_cli("memory", "list", "--profile-root", str(tmp_path), "--json")

    assert draft_result.returncode == 0, draft_result.stderr
    assert list_result.returncode == 0, list_result.stderr
    draft_payload = json.loads(draft_path.read_text(encoding="utf-8"))
    list_payload = json.loads(list_result.stdout)
    assert draft_payload["memory"][0]["key"] == "tool:agent-tools"
    assert list_payload["memory"] == []


def test_apply_draft_replaces_existing_memory_key(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(
        json.dumps(
            {
                "memory": [
                    {
                        "key": "tool:agent-tools",
                        "scope": "tool-registry",
                        "text": "Updated memory SERVICE_TOKEN=private",
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    first_result = _run_cli(
        "memory",
        "upsert",
        "--profile-root",
        str(tmp_path),
        "--key",
        "tool:agent-tools",
        "--scope",
        "tool-registry",
        "--text",
        "Old memory",
        "--json",
    )
    apply_result = _run_cli(
        "memory",
        "apply-draft",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(draft_path),
        "--json",
    )
    list_result = _run_cli("memory", "list", "--profile-root", str(tmp_path), "--json")

    assert first_result.returncode == 0, first_result.stderr
    assert apply_result.returncode == 0, apply_result.stderr
    memory = json.loads(list_result.stdout)["memory"]
    assert memory == [
        {
            "key": "tool:agent-tools",
            "scope": "tool-registry",
            "text": "Updated memory [redacted]",
        },
    ]


def test_apply_draft_rejects_empty_memory_entries(tmp_path: Path) -> None:
    draft_path = tmp_path / "empty.json"
    draft_path.write_text(json.dumps({"memory": []}), encoding="utf-8")

    result = _run_cli(
        "memory",
        "apply-draft",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(draft_path),
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "INVALID_MEMORY_DRAFT"


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
    )
