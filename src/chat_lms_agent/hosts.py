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

DESIGN_GENERATION_DEFAULT_ENGINE_ID: Final = "codex"
DESIGN_GENERATION_DEFAULT_CLI: Final = "codex"
DESIGN_GENERATION_DEFAULT_EXEC_ARGS: Final = ("exec",)
DESIGN_GENERATION_DEFAULT_NOT_FOUND_CODE: Final = "CODEX_CLI_NOT_FOUND"
DESIGN_GENERATION_DEFAULT_TIMEOUT_CODE: Final = "CODEX_CLI_TIMEOUT"
DESIGN_GENERATION_DEFAULT_FAILED_CODE: Final = "CODEX_CLI_FAILED"
DESIGN_GENERATION_DEFAULT_MISSING_ARTIFACT_MESSAGE: Final = (
    "codex response did not contain a complete HTML artifact"
)
DESIGN_GENERATION_DEFAULT_NOT_FOUND_MESSAGE: Final = "codex CLI was not found on PATH"
DESIGN_GENERATION_DEFAULT_TIMEOUT_MESSAGE: Final = (
    "codex exec timed out while generating the side-panel design"
)
DESIGN_GENERATION_DEFAULT_FAILED_MESSAGE: Final = "codex exec returned a non-zero exit code"
DESIGN_GENERATION_DEFAULT_AUTH_HINT: Final = (
    "Install or open the Codex CLI and sign in with ChatGPT OAuth; no API key is needed."
)
DESIGN_GENERATION_DEFAULT_SUCCESS_NOTE: Final = "codex exec"


def active_host() -> HostAdapter:
    return CODEX_DESKTOP
