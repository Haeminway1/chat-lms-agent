from __future__ import annotations

from pathlib import Path

from chat_lms_agent.cli_io import option, subcommand, write_json
from chat_lms_agent.skills import skills_payload, skills_validation_payload


def handle_skills(args: list[str], repo_root: Path) -> int:
    command = subcommand(args)
    root_override = _root_override(args)
    if command == "list":
        write_json(skills_payload(repo_root, root_override))
        return 0
    if command == "validate":
        code, payload = skills_validation_payload(repo_root, root_override)
        write_json(payload)
        return code
    write_json({"status": "ERROR", "error_code": "UNKNOWN_SKILLS_COMMAND"})
    return 2


def _root_override(args: list[str]) -> Path | None:
    root = option(args, "--root")
    if root is None:
        return None
    return Path(root)
