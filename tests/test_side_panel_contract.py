from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_side_panel_spec_json_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_cli("side-panel", "spec", "--json", cwd=repo_root)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["official_name"] == "보조 패널(side panel)"
    assert payload["design_reference"] == "user-provided-html-prototype"
    assert payload["user_owned_html_css"] is True
    assert payload["views"] == [
        "class_overview",
        "learner_detail",
        "attendance_summary",
        "session_record",
        "homework_status",
    ]
    assert payload["section_types"] == [
        "summary",
        "metric_grid",
        "entity_list",
        "timeline",
        "task_list",
        "action_group",
    ]
    traits = payload["traits"]
    assert traits["required"][0] == "header_metadata"
    assert "A/B/C" in traits["recommended"]


def test_side_panel_spec_includes_wordbook_runtime_route() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_cli("side-panel", "spec", "--json", cwd=repo_root)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    runtime_routes = payload["runtime_routes"]
    assert "lesson_panel" not in runtime_routes
    route = runtime_routes["lesson_wordbook"]
    assert route["first_command"].startswith("side-panel wordbook open-plan")
    assert route["ensure_command"].startswith("side-panel wordbook ensure-server")
    assert route["file_search_policy"] == "do_not_rg_before_cli_route"


def test_side_panel_block_list() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_cli("side-panel", "block", "list", "--json", cwd=repo_root)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"

    blocks = payload["blocks"]
    assert "SidePanelShell" in blocks
    assert "PanelChrome" in blocks
    assert "ViewTabs" in blocks
    assert len(blocks) >= 13


def test_view_draft_returns_pass_for_known_view() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_cli(
        "side-panel",
        "view",
        "draft",
        "--view",
        "class_overview",
        "--json",
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["view"] == "class_overview"
    assert payload["recommended_variant"] == "b"
    assert payload["required_sections"]
    assert (
        payload["memory_obligation"]
        == "SIDE_PANEL_MEMORY_REQUIRED:side_panel:view:class_overview"
    )


def test_view_draft_unknown_view_requests_proposal() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_cli(
        "side-panel",
        "view",
        "draft",
        "--view",
        "home_room_finder",
        "--json",
        cwd=repo_root,
    )

    assert result.returncode in {2, 3}
    payload = json.loads(result.stdout)
    assert payload["status"] == "PROPOSAL_REQUIRED"
    assert "proposal" in payload
    assert "html" not in payload
    assert "css" not in payload


def test_payload_validate_accepts_valid_synthetic_payload(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = {
        "schema_version": "0.1.0",
        "view_id": "class_overview",
        "title": "6-3A",
        "subtitle": "반 테스트반",
        "entity_ref": "class:6-3A",
        "generated_at": "2026-06-09T09:00:00+09:00",
        "privacy_level": "class",
        "synthetic": True,
        "sections": [
            {
                "type": "summary",
                "text": "주간 보강 현황",
            },
            {
                "type": "action_group",
                "actions": [
                    {
                        "label": "출석 명부 갱신",
                        "intent": "open_report",
                        "requires_approval": True,
                        "dry_run_default": False,
                    },
                ],
            },
        ],
        "design_tokens": {
            "theme": "light",
            "accent": "#3182F6",
            "density": "roomy",
            "round": "soft",
            "fontSize": 15,
        },
    }
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _run_cli(
        "side-panel",
        "payload",
        "validate",
        "--from",
        str(payload_path),
        "--json",
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_payload_validate_accepts_utf8_bom_payload(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = {
        "schema_version": "0.1.0",
        "view_id": "class_overview",
        "title": "Synthetic Class",
        "subtitle": "Public-safe fixture",
        "entity_ref": "class:synthetic",
        "generated_at": "2026-06-09T09:00:00+09:00",
        "privacy_level": "class",
        "synthetic": True,
        "sections": [
            {
                "type": "summary",
                "text": "Synthetic summary",
            },
            {
                "type": "action_group",
                "actions": [
                    {
                        "label": "Open report",
                        "intent": "open_report",
                        "requires_approval": True,
                        "dry_run_default": False,
                    },
                ],
            },
        ],
    }
    payload_path = tmp_path / "payload-with-bom.json"
    payload_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8-sig",
    )

    result = _run_cli(
        "side-panel",
        "payload",
        "validate",
        "--from",
        str(payload_path),
        "--json",
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


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
