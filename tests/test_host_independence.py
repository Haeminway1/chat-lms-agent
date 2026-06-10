from __future__ import annotations

import re
from pathlib import Path

from chat_lms_agent.hosts import active_host

# Catches host-coupling token forms ("Codex", "codex-workspace", ".codex-plugin",
# "codex_desktop", "build_codex_context", "--for-codex") while ignoring OSS
# project names like "lazycodex" that merely contain the substring.
_HOST_TOKEN_RE = re.compile(r"(?i)\bcodex\b|codex[-_]|[-_.]codex")

# The only modules allowed to know the host by name:
# - hosts.py: the adapter data itself
# - oss_references.py: pinned external-reference registry data
# - command_parser.py: the host-dialect CLI compat flag (--for-codex)
_ALLOWED_HOST_FILES = {"hosts.py", "oss_references.py", "command_parser.py"}


def test_core_modules_are_host_token_free() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "chat_lms_agent"
    offenders: dict[str, list[str]] = {}
    for path in sorted(src.glob("*.py")):
        if path.name in _ALLOWED_HOST_FILES:
            continue
        hits = [
            f"{line_number}: {line.strip()}"
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            )
            if _HOST_TOKEN_RE.search(line)
        ]
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"host tokens leaked into core modules: {offenders}"


def test_host_adapter_declares_identity_and_future_hosts() -> None:
    host = active_host()
    assert host.host_id == "codex_desktop"
    assert host.agent_actor == "codex_desktop_agent"
    assert host.runtime_label == "Codex Desktop"
    assert host.workspace_dirname == "codex-workspace"
    assert "standalone_desktop" in host.future_hosts
    assert "web_saas" in host.future_hosts
    assert host.host_files
