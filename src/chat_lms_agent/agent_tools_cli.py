from __future__ import annotations

import sys

from chat_lms_agent.commands import main


def app() -> None:
    raise SystemExit(main(["agent-tools", *sys.argv[1:]]))
