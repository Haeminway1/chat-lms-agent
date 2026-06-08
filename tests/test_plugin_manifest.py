from __future__ import annotations

import json
from pathlib import Path


def test_plugin_manifest_describes_codex_desktop_product() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / ".codex-plugin" / "plugin.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "chat-lms-agent"
    assert "Codex Desktop" in manifest["description"]
    assert manifest["version"] == "0.1.0"
