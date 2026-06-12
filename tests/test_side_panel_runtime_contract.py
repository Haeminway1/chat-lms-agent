from __future__ import annotations

from pathlib import Path

from chat_lms_agent.side_panel_wordbook import ensure_wordbook_server, wordbook_open_plan
from chat_lms_agent.state import ProfileState


def test_wordbook_missing_assets_payload_contract_remains_stable(tmp_path: Path) -> None:
    # Given: a profile without wordbook runtime assets.
    profile = _profile_state(tmp_path)

    # When: the wordbook runtime is planned.
    code, payload = wordbook_open_plan(profile, "Synthetic Learner", None, 8765)

    # Then: the missing-runtime JSON shape remains byte-identical.
    assert code == 4
    assert payload == {
        "status": "BLOCKED",
        "error_code": "WORDBOOK_RUNTIME_MISSING",
        "message": "private profile does not contain lesson wordbook runtime assets",
        "runtime_assets": {
            "server": "<profile-root>/codex-workspace/scripts/lesson_wordbook_server.py",
            "view": "<profile-root>/codex-workspace/scripts/lesson_wordbook_view.html",
        },
    }


def test_wordbook_open_plan_not_running_payload_contract_remains_stable(
    tmp_path: Path,
) -> None:
    # Given: wordbook runtime assets exist but no server is listening on a custom port.
    profile = _profile_state(tmp_path)
    _write_wordbook_assets(tmp_path)
    port = 9

    # When: open-plan probes that port.
    code, payload = wordbook_open_plan(profile, "Synthetic Learner", "2026-06-12", port)

    # Then: the public payload shape remains stable.
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["kind"] == "lesson_wordbook"
    assert payload["student"] == "Synthetic Learner"
    assert payload["browser_url"] == (
        "http://127.0.0.1:9/?student=Synthetic+Learner&date=2026-06-12"
    )
    assert payload["server"]["status"] == "not_running"
    assert payload["supported_runtime_port"] == 8765
    assert payload["next_action"] == "use_default_wordbook_port_or_connect_running_runtime"


def test_wordbook_ensure_custom_port_contract_remains_stable(tmp_path: Path) -> None:
    # Given: wordbook runtime assets exist and a custom unused port is requested.
    profile = _profile_state(tmp_path)
    _write_wordbook_assets(tmp_path)

    # When: ensure-server is called for a non-default port.
    code, payload = ensure_wordbook_server(profile, 9, dry_run=False)

    # Then: the unsupported custom-port contract remains stable.
    assert code == 5
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "WORDBOOK_PORT_UNSUPPORTED"
    assert payload["message"] == "lesson wordbook runtime currently starts on port 8765"
    assert payload["supported_runtime_port"] == 8765
    assert payload["server"]["status"] == "not_running"


def _write_wordbook_assets(profile_root: Path) -> None:
    scripts = profile_root / "codex-workspace" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "lesson_wordbook_server.py").write_text("print('synthetic')\n", encoding="utf-8")
    (scripts / "lesson_wordbook_view.html").write_text("<html></html>\n", encoding="utf-8")


def _profile_state(profile_root: Path) -> ProfileState:
    return ProfileState(root=profile_root.resolve(), repo_root=Path(__file__).resolve().parents[1])
