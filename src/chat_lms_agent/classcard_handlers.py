"""ClassCard CLI handler (optional extra).

Phase A wires the checkpoint-driven flows that run standalone: a saved
upload run (manifest + checkpoint) replayed headlessly, audio repair, and
one-time credential capture. The DB-integrated planning flow
(prepare/execute straight from the academy DB) is Phase B and is not wired
yet. Playwright is imported lazily so the core harness stays installable
without the [classcard] extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import option, required_option, subcommand, write_json

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

_PLAYWRIGHT_HINT = (
    "ClassCard automation needs the optional extra: "
    "uv pip install chat-lms-agent[classcard] && playwright install chromium"
)


def handle_classcard(args: list[str], repo_root: Path) -> int:
    _ = repo_root
    command = subcommand(args)
    if command == "login":
        return _login(args)
    if command == "direct-upload":
        return _direct_upload(args)
    if command == "direct-repair-audio":
        return _direct_repair_audio(args)
    if command in {"upload", "recover", "verify"}:
        write_json(
            {
                "status": "ERROR",
                "error_code": "CLASSCARD_DB_FLOW_NOT_WIRED",
                "message": (
                    "DB-integrated classcard flow is Phase B; use direct-upload "
                    "with a prepared checkpoint for now."
                ),
            },
        )
        return 2
    write_json({"status": "ERROR", "error_code": "UNKNOWN_CLASSCARD_COMMAND"})
    return 2


def _login(args: list[str]) -> int:
    try:
        from chat_lms_agent.classcard_login import (
            default_credentials_path,
            save_classcard_credentials,
        )
    except ImportError:
        return _playwright_missing()
    username = option(args, "--username")
    password = option(args, "--password")
    if username is None or password is None:
        write_json(
            {
                "status": "NEEDS_INPUT",
                "error_code": "CLASSCARD_CREDENTIALS_REQUIRED",
                "message_ko": (
                    "최초 1회만: --username 과 --password 로 classcard 로그인 정보를 저장하세요. "
                    "이후에는 영속 프로필로 자동 로그인됩니다."
                ),
                "stored_at": str(default_credentials_path()),
            },
        )
        return 2
    path = save_classcard_credentials(username, password)
    write_json({"status": "PASS", "stored_at": str(path)})
    return 0


def _direct_upload(args: list[str]) -> int:
    try:
        from chat_lms_agent.classcard_direct_upload import _load_run, upload_missing_parts
    except ImportError:
        return _playwright_missing()
    run = _load_run(
        required_option(args, "--checkpoint"),
        required_option(args, "--class-url"),
        option(args, "--credentials"),
        option(args, "--profile-dir"),
    )
    results = upload_missing_parts(run)
    payload: dict[str, JsonValue] = {
        "status": "PASS" if results["status"] == "completed" else "ERROR",
        "classcard_status": results["status"],
        "completed_indexes": results["completed_indexes"],
    }
    write_json(payload)
    return 0 if results["status"] == "completed" else 1


def _direct_repair_audio(args: list[str]) -> int:
    try:
        from chat_lms_agent.classcard_direct_repair import repair_set_audio_paths
    except ImportError:
        return _playwright_missing()
    result = repair_set_audio_paths(
        required_option(args, "--set-id"),
        credentials=option(args, "--credentials"),
        profile_dir=option(args, "--profile-dir"),
    )
    write_json(
        {
            "status": "PASS" if result["status"] == "completed" else "ERROR",
            "set_idx": result.get("set_idx"),
            "word_count": result.get("word_count"),
        },
    )
    return 0


def _playwright_missing() -> int:
    write_json(
        {
            "status": "ERROR",
            "error_code": "CLASSCARD_EXTRA_NOT_INSTALLED",
            "message": _PLAYWRIGHT_HINT,
        },
    )
    return 2
