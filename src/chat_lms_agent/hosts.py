"""Host adapter data: the single place that knows which host runs the harness.

Core modules read host identity (actor name, runtime label, workspace
directory, host-owned files) from the active adapter instead of hardcoding
it, so a future standalone desktop or web SaaS host is a new adapter, not a
core rewrite. Enforced by ``tests/test_host_independence.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class HostAdapter:
    host_id: str
    agent_actor: str
    runtime_label: str
    workspace_dirname: str
    host_files: tuple[str, ...]
    future_hosts: tuple[str, ...]


CODEX_DESKTOP: Final = HostAdapter(
    host_id="codex_desktop",
    agent_actor="codex_desktop_agent",
    runtime_label="Codex Desktop",
    workspace_dirname="codex-workspace",
    host_files=(".codex-plugin/plugin.json", "hooks/hooks.json"),
    future_hosts=("standalone_desktop", "web_saas"),
)


def active_host() -> HostAdapter:
    return CODEX_DESKTOP
