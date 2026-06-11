"""ClassCard CLI handler (optional extra).

The checkpoint-driven flows (direct-upload, direct-repair-audio, login)
run standalone; the DB-integrated planning flow (upload/recover/verify)
reads the teacher's profile database — the same ``tutoring_*`` tables the
side-panel wordbook writes — and drives the proven headless uploader.
Playwright is imported lazily so the core harness stays installable
without the [classcard] extra.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import (
    flag,
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

_PLAYWRIGHT_HINT = (
    "ClassCard automation needs the optional extra: "
    "uv pip install chat-lms-agent[classcard] && playwright install chromium"
)


def handle_classcard(args: list[str], repo_root: Path) -> int:
    command = subcommand(args)
    if command == "login":
        return _login(args)
    if command == "direct-upload":
        return _direct_upload(args)
    if command == "direct-repair-audio":
        return _direct_repair_audio(args)
    if command == "upload":
        return _upload(args, repo_root)
    if command == "recover":
        return _recover(args)
    if command == "verify":
        return _verify(args)
    write_json({"status": "ERROR", "error_code": "UNKNOWN_CLASSCARD_COMMAND"})
    return 2


def _upload(args: list[str], repo_root: Path) -> int:
    try:
        from chat_lms_agent.classcard import execute_upload, prepare_upload
        from chat_lms_agent.classcard_plan import parse_classcard_mode
    except ImportError:
        return _playwright_missing()
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    db_path = _db_path(args, profile)
    if db_path is None:
        return 2
    student = required_option(args, "--student")
    checkpoint = option(args, "--checkpoint") or str(
        profile.root / STATE_DIR / "classcard" / f"{student}.checkpoint.json",
    )
    raw_mode = option(args, "--mode")
    mode = parse_classcard_mode(raw_mode) if raw_mode else None
    span_days_raw = option(args, "--span-days")
    span_days = int(span_days_raw) if span_days_raw else None
    if flag(args, "--execute"):
        result = execute_upload(
            db_path,
            student,
            checkpoint,
            lesson_date=option(args, "--lesson-date"),
            mode=mode,
            span_days=span_days,
            out_dir=option(args, "--out-dir"),
            browser_options=_browser_options(args),
        )
        write_json(
            {
                "status": "PASS" if result.status == "completed" else "ERROR",
                "classcard_status": result.status,
                "checkpoint": str(result.checkpoint_path),
            },
        )
        return 0 if result.status == "completed" else 1
    prepared = prepare_upload(
        db_path,
        student,
        checkpoint,
        lesson_date=option(args, "--lesson-date"),
        mode=mode,
        span_days=span_days,
        out_dir=option(args, "--out-dir"),
    )
    write_json(
        {
            "status": "PASS",
            "classcard_status": prepared.status,
            "mode": prepared.plan.mode.value,
            "parts": len(prepared.plan.parts),
            "checkpoint": str(prepared.checkpoint_path),
            "manifest": str(prepared.manifest_path),
            "next_command": (
                "python -m chat_lms_agent classcard upload --student "
                f"{student} --execute --profile-root <root> --json"
            ),
        },
    )
    return 0


def _recover(args: list[str]) -> int:
    try:
        from chat_lms_agent.classcard import recover_upload, resume_execute_upload
    except ImportError:
        return _playwright_missing()
    checkpoint = required_option(args, "--checkpoint")
    if flag(args, "--execute"):
        result = resume_execute_upload(checkpoint, browser_options=_browser_options(args))
        write_json(
            {
                "status": "PASS" if result.status == "completed" else "ERROR",
                "classcard_status": result.status,
                "checkpoint": str(result.checkpoint_path),
            },
        )
        return 0 if result.status == "completed" else 1
    result = recover_upload(checkpoint)
    write_json(
        {
            "status": "PASS",
            "classcard_status": result.status,
            "checkpoint": str(result.checkpoint_path),
        },
    )
    return 0


def _verify(args: list[str]) -> int:
    try:
        from chat_lms_agent.classcard_verify_command import verify_checkpoint_with_playwright
    except ImportError:
        return _playwright_missing()
    result = verify_checkpoint_with_playwright(
        required_option(args, "--checkpoint"),
        required_option(args, "--class-url"),
        browser_options=_browser_options(args),
    )
    completed: list[JsonValue] = []
    completed.extend(result.completed_indexes)
    missing: list[JsonValue] = []
    missing.extend(result.missing_indexes)
    write_json(
        {
            "status": "PASS" if not result.missing_indexes else "ERROR",
            "classcard_status": result.status.value,
            "completed_indexes": completed,
            "missing_indexes": missing,
        },
    )
    return 0 if not result.missing_indexes else 1


def _db_path(args: list[str], profile: ProfileState) -> str | None:
    override = option(args, "--db")
    if override is not None:
        return override
    default = profile.root / "data" / "chat_lms.db"
    if not default.exists():
        write_json(
            {
                "status": "ERROR",
                "error_code": "CLASSCARD_DB_NOT_FOUND",
                "message_ko": (
                    "프로필에 data/chat_lms.db 가 없습니다. --db 로 경로를 지정하세요."
                ),
            },
        )
        return None
    return str(default)


def _browser_options(args: list[str]) -> object:
    from chat_lms_agent.classcard_browser import ClasscardBrowserOptions

    profile_dir = option(args, "--profile-dir")
    slow_mo_raw = option(args, "--slow-mo-ms")
    return ClasscardBrowserOptions(
        profile_dir=Path(profile_dir) if profile_dir else None,
        headed=flag(args, "--headed"),
        slow_mo_ms=int(slow_mo_raw) if slow_mo_raw else 0,
    )


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
