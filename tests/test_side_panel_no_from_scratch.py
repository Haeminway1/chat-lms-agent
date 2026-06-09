from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_unknown_view_creates_proposal_not_html() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_cli(
        "side-panel",
        "view",
        "draft",
        "--view",
        "heroic_summary_view",
        "--json",
        cwd=repo_root,
    )

    assert result.returncode in {2, 3}
    payload = json.loads(result.stdout)
    assert payload["status"] == "PROPOSAL_REQUIRED"
    assert "html" not in payload
    assert "css" not in payload


def test_raw_prototype_files_are_not_required_public_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    forbidden_names = {
        "보조 패널.html",
        "app.jsx",
        "styles.css",
    }
    ignored_parts = {".git", ".mypy_cache", ".omo", ".pytest_cache", ".ruff_cache", ".venv"}

    hits: list[str] = []
    for path in repo_root.rglob("*"):
        relative_parts = path.relative_to(repo_root).parts
        if any(part in ignored_parts for part in relative_parts):
            continue
        if not path.is_file():
            continue
        if path.name in forbidden_names or "screenshots" in relative_parts:
            hits.append(str(path.relative_to(repo_root)))
    if hits:
        message = "raw prototype artifacts must not exist in public repo: "
        raise AssertionError(message + ", ".join(hits))


def test_actions_require_intent_approval_and_dry_run_policy() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = {
        "schema_version": "0.1.0",
        "view_id": "class_overview",
        "title": "7-1A",
        "subtitle": "반 테스트반",
        "entity_ref": "class:7-1A",
        "generated_at": "2026-06-09T09:00:00+09:00",
        "privacy_level": "class",
        "source_commands": [
            {
                "command": "academy class show",
                "query_name": "class_overview",
            },
        ],
        "sections": [
            {
                "type": "action_group",
                "actions": [
                    {
                        "label": "보강 배정",
                    },
                ],
            },
        ],
    }

    payload_path = repo_root / "_tmp_side_panel_payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        result = _run_cli(
            "side-panel",
            "payload",
            "validate",
            "--from",
            str(payload_path),
            "--json",
            cwd=repo_root,
        )
    finally:
        payload_path.unlink()

    assert result.returncode == 2
    payload_out = json.loads(result.stdout)
    assert payload_out["status"] == "ERROR"
    assert any("intent" in item for item in payload_out["errors"])
    assert any("requires_approval" in item for item in payload_out["errors"])
    assert any("dry_run_default" in item for item in payload_out["errors"])


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
