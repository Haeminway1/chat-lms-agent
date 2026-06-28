from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from chat_lms_agent import approvals
from chat_lms_agent.cli_io import (
    flag,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.schedule import (
    JobPlan,
    action_to_json,
    build_job_plan,
    job_plan_to_json,
    redacted_run_log_record,
    scheduled_job,
)
from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from chat_lms_agent.schedule_backend import TaskSchedulerBackend
    from chat_lms_agent.state import JsonValue, ProfileState


def handle_schedule(
    args: list[str],
    repo_root: Path,
    *,
    backend: TaskSchedulerBackend,
) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    command = subcommand(args)
    handlers: dict[str, Callable[[], int]] = {
        "plan": lambda: _plan(args, repo_root, profile),
        "register": lambda: _register(args, repo_root, profile, backend),
        "list": lambda: _list(backend),
        "status": lambda: _status(args, backend),
        "runs": lambda: _runs(profile),
        "remove": lambda: _remove(args, backend),
        "run-now": lambda: _run_now(args, profile),
    }
    handler = handlers.get(command)
    if handler is None:
        write_json({"status": "ERROR", "error_code": "UNKNOWN_SCHEDULE_COMMAND"})
        return 2
    return handler()


def _plan(args: list[str], repo_root: Path, profile: ProfileState) -> int:
    result = _build_plan_from_args(args, repo_root, profile)
    if isinstance(result, str):
        write_json({"status": "ERROR", "error_code": result})
        return 2
    write_json(
        {
            "status": "PASS",
            "dry_run": True,
            "job": job_plan_to_json(result),
            "action": action_to_json(result.action),
        },
    )
    return 0


def _register(
    args: list[str],
    repo_root: Path,
    profile: ProfileState,
    backend: TaskSchedulerBackend,
) -> int:
    result = _build_plan_from_args(args, repo_root, profile)
    if isinstance(result, str):
        write_json({"status": "ERROR", "error_code": result})
        return 2
    approval_id = approvals.approval_id_for(result.plan_id)
    if not approvals.approval_is_approved(profile, approval_id, result.plan_id):
        request = approvals.ensure_approval_request(
            profile,
            plan_id=result.plan_id,
            operation="schedule register",
        )
        write_json(
            {
                "status": "NEEDS_APPROVAL",
                "approval_id": request["approval_id"],
                "plan_id": result.plan_id,
                "job": job_plan_to_json(result),
            },
        )
        return 3
    backend.upsert_job(scheduled_job(result))
    write_json(
        {
            "status": "PASS",
            "dry_run": True,
            "job": job_plan_to_json(result),
            "action": action_to_json(result.action),
        },
    )
    return 0


def _list(backend: TaskSchedulerBackend) -> int:
    jobs: list[JsonValue] = [
        {
            "job_id": job.job_id,
            "job_name": job.job_name,
            "trigger": dict(job.trigger),
            "action": action_to_json(job.action),
        }
        for job in backend.list_jobs()
    ]
    write_json({"status": "PASS", "jobs": jobs})
    return 0


def _status(args: list[str], backend: TaskSchedulerBackend) -> int:
    job_id = required_option(args, "--id")
    for job in backend.list_jobs():
        if job.job_id == job_id:
            write_json({"status": "PASS", "job_id": job.job_id, "job_name": job.job_name})
            return 0
    write_json({"status": "ERROR", "error_code": "UNKNOWN_SCHEDULE_JOB"})
    return 2


def _runs(profile: ProfileState) -> int:
    write_json({"status": "PASS", "runs": _read_run_log(profile)})
    return 0


def _remove(args: list[str], backend: TaskSchedulerBackend) -> int:
    job_name = required_option(args, "--name")
    removed = backend.remove_job(job_name)
    write_json({"status": "PASS", "removed": removed, "job_name": job_name})
    return 0


def _run_now(args: list[str], profile: ProfileState) -> int:
    job_id = required_option(args, "--id")
    _append_run_log(
        profile,
        redacted_run_log_record(
            job_id=job_id,
            outcome="needs_human",
            detail=f"{job_id} needs a registered dry-run schedule job",
        ),
    )
    write_json({"status": "NEEDS_HUMAN", "job_id": job_id})
    return 3


def _build_plan_from_args(
    args: list[str],
    repo_root: Path,
    profile: ProfileState,
) -> JobPlan | str:
    try:
        kind = _required_schedule_option(args, "--kind", "MISSING_KIND")
        if kind == "shell":
            return "UNSUPPORTED_SCHEDULE_KIND"
        if flag(args, "--execute") or flag(args, "--unattended-execute"):
            return "SCHEDULE_EXECUTE_UNSUPPORTED"
        trigger_at = _required_schedule_option(args, "--at", "MISSING_AT")
        return build_job_plan(
            profile,
            repo_root,
            kind=kind,
            args=_schedule_args(args, kind),
            trigger={"at": trigger_at},
        )
    except ValueError as error:
        return str(error)


def _schedule_args(args: list[str], kind: str) -> dict[str, str]:
    match kind:
        case "shortcut":
            return {"name": _required_schedule_option(args, "--name", "MISSING_NAME")}
        case "write-action":
            return {
                "id": _required_schedule_option(args, "--id", "MISSING_ID"),
                "from": _required_schedule_option(args, "--from", "MISSING_FROM"),
            }
        case "outbound":
            return _outbound_args(args)
        case _:
            return {}


def _outbound_args(args: list[str]) -> dict[str, str]:
    schedule_args = {
        "target": _required_schedule_option(args, "--target", "MISSING_TARGET"),
        "database": _required_schedule_option(args, "--database", "MISSING_DATABASE"),
        "out_dir": _required_schedule_option(args, "--out-dir", "MISSING_OUT_DIR"),
    }
    for flag_name, key in (
        ("--date", "date"),
        ("--from", "from"),
        ("--to", "to"),
        ("--source-key", "source_key"),
        ("--classes", "classes"),
        ("--token-file", "token_file"),
    ):
        value = _optional(args, flag_name)
        if value is not None:
            schedule_args[key] = value
    return schedule_args


def _required_schedule_option(args: list[str], flag_name: str, error_code: str) -> str:
    value = _optional(args, flag_name)
    if value is None:
        raise ValueError(error_code)
    return value


def _optional(args: list[str], flag_name: str) -> str | None:
    for index, arg in enumerate(args[:-1]):
        if arg == flag_name:
            return args[index + 1]
    return None


def _append_run_log(profile: ProfileState, record: dict[str, JsonValue]) -> None:
    path = _run_log_path(profile)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        existing = _read_log_text(path)
        content = (existing + line)[-128_000:]
        _ = path.write_text(content, encoding="utf-8")
    except OSError:
        return


def _read_run_log(profile: ProfileState) -> list[JsonValue]:
    path = _run_log_path(profile)
    if not path.exists():
        return []
    try:
        return [
            cast("JsonValue", json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []


def _run_log_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "schedule" / "runs.jsonl"


def _read_log_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
