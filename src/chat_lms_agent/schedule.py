from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from chat_lms_agent.hosts import active_host
from chat_lms_agent.schedule_backend import ScheduledAction, ScheduledJob

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

SCHEDULE_SCHEMA_VERSION: Final = "schedule-v1"
JOB_PREFIX: Final = "ChatLMS"
RUN_LOG_MAX_BYTES: Final = 128_000
OUTBOUND_SYNC_TARGETS: Final = frozenset({"daily-management", "daily-lesson-homework"})

_PROFILE_SLUG_RE: Final = re.compile(r"[^A-Za-z0-9]+")
_PII_NAME_RE: Final = re.compile(r"\bFictional\s+[A-Z][A-Za-z]+\b")
_NUMBER_RE: Final = re.compile(r"\d{2,}")


@dataclass(frozen=True, slots=True)
class JobPlan:
    job_id: str
    plan_id: str
    job_name: str
    kind: str
    args: dict[str, str]
    trigger: dict[str, JsonValue]
    action: ScheduledAction


def build_job_plan(
    profile: ProfileState,
    repo_root: Path,
    *,
    kind: str,
    args: dict[str, str],
    trigger: dict[str, JsonValue],
) -> JobPlan:
    normalized_kind = kind.strip()
    if normalized_kind == "shortcut":
        message = "SCHEDULE_SHORTCUT_DRY_RUN_UNSAFE"
        raise ValueError(message)
    if normalized_kind not in {"write-action", "outbound"}:
        message = "UNSUPPORTED_SCHEDULE_KIND"
        raise ValueError(message)
    action = _action_for_kind(profile, repo_root, normalized_kind, args)
    content = {
        "schema_version": SCHEDULE_SCHEMA_VERSION,
        "profile_root": str(profile.root.resolve()),
        "kind": normalized_kind,
        "args": args,
        "trigger": trigger,
        "argv": action.argv,
    }
    digest = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8"),
    ).hexdigest()
    job_id = f"{normalized_kind}-{digest[:16]}"
    return JobPlan(
        job_id=job_id,
        plan_id=f"schedule:{job_id}",
        job_name=f"{job_name_prefix(profile)}{digest[:12]}",
        kind=normalized_kind,
        args=args,
        trigger=trigger,
        action=action,
    )


def scheduled_job(plan: JobPlan) -> ScheduledJob:
    return ScheduledJob(
        job_id=plan.job_id,
        job_name=plan.job_name,
        trigger=plan.trigger,
        action=plan.action,
    )


def job_plan_to_json(plan: JobPlan) -> dict[str, JsonValue]:
    return {
        "schema_version": SCHEDULE_SCHEMA_VERSION,
        "job_id": plan.job_id,
        "plan_id": plan.plan_id,
        "job_name": plan.job_name,
        "kind": plan.kind,
        "args": dict(plan.args),
        "trigger": dict(plan.trigger),
    }


def action_to_json(action: ScheduledAction) -> dict[str, JsonValue]:
    argv: list[JsonValue] = []
    argv.extend(action.argv)
    return {"argv": argv, "env": dict(action.env)}


def redacted_run_log_record(
    *,
    job_id: str,
    outcome: str,
    detail: str,
) -> dict[str, JsonValue]:
    return {
        "schema_version": SCHEDULE_SCHEMA_VERSION,
        "ts": datetime.now(tz=UTC).isoformat(),
        "job_id": job_id,
        "outcome": outcome,
        "detail": _redact_detail(detail),
    }


def _action_for_kind(
    profile: ProfileState,
    repo_root: Path,
    kind: str,
    args: dict[str, str],
) -> ScheduledAction:
    _ = repo_root
    profile_root = str(profile.root.resolve())
    wrapper = (
        profile.root.resolve()
        / active_host().workspace_dirname
        / "scripts"
        / "chat-lms-cli.ps1"
    )
    base = (
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(wrapper),
    )
    profile_args = ("--profile-root", profile_root)
    match kind:
        case "write-action":
            template_id = _required_arg(args, "id")
            source = str(Path(_required_arg(args, "from")).resolve())
            command_args = (
                "write-action",
                "plan",
                "--id",
                template_id,
                "--from",
                source,
                *profile_args,
                "--json",
            )
        case "outbound":
            target = _required_arg(args, "target")
            command_args = _outbound_sync_args(target, args, profile_args)
        case _:
            message = "UNSUPPORTED_SCHEDULE_KIND"
            raise ValueError(message)
    return ScheduledAction(
        argv=(*base, *command_args),
        env={"CHAT_LMS_AGENT_PROFILE_ROOT": profile_root},
    )


def _outbound_sync_args(
    target: str,
    args: dict[str, str],
    profile_args: tuple[str, str],
) -> tuple[str, ...]:
    match target:
        case "daily-management":
            return _daily_management_sync_args(target, args, profile_args)
        case "daily-lesson-homework":
            return _daily_lesson_homework_sync_args(target, args, profile_args)
        case _:
            message = "UNSUPPORTED_OUTBOUND_TARGET"
            raise ValueError(message)


def _base_outbound_sync_args(
    target: str,
    args: dict[str, str],
    profile_args: tuple[str, str],
) -> list[str]:
    command: list[str] = [
        "outbound",
        target,
        "sync",
        "--database",
        str(Path(_required_arg(args, "database")).resolve()),
        "--out-dir",
        str(Path(_required_arg(args, "out_dir")).resolve()),
        *profile_args,
        "--json",
    ]
    return command


def _daily_management_sync_args(
    target: str,
    args: dict[str, str],
    profile_args: tuple[str, str],
) -> tuple[str, ...]:
    _reject_present(args, "classes")
    command = _base_outbound_sync_args(target, args, profile_args)
    date_value = args.get("date", "").strip()
    from_value = args.get("from", "").strip()
    to_value = args.get("to", "").strip()
    if date_value:
        command.extend(("--date", date_value))
    elif from_value and to_value:
        command.extend(("--from", from_value, "--to", to_value))
    else:
        message = "MISSING_OUTBOUND_DATE_RANGE"
        raise ValueError(message)
    _append_optional_arg(command, "--source-key", args.get("source_key", ""))
    _append_optional_path_arg(command, "--token-file", args.get("token_file", ""))
    return tuple(command)


def _daily_lesson_homework_sync_args(
    target: str,
    args: dict[str, str],
    profile_args: tuple[str, str],
) -> tuple[str, ...]:
    _reject_present(args, "from")
    _reject_present(args, "to")
    command = _base_outbound_sync_args(target, args, profile_args)
    command.extend(("--date", _required_arg(args, "date")))
    _append_optional_arg(command, "--source-key", args.get("source_key", ""))
    _append_optional_arg(command, "--classes", args.get("classes", ""))
    _append_optional_path_arg(command, "--token-file", args.get("token_file", ""))
    return tuple(command)


def _reject_present(args: dict[str, str], key: str) -> None:
    if args.get(key, "").strip():
        message = "UNSUPPORTED_OUTBOUND_ARG"
        raise ValueError(message)


def _append_optional_arg(command: list[str], flag_name: str, value: str) -> None:
    if value.strip():
        command.extend((flag_name, value.strip()))


def _append_optional_path_arg(command: list[str], flag_name: str, value: str) -> None:
    if value.strip():
        command.extend((flag_name, str(Path(value).resolve())))


def _required_arg(args: dict[str, str], name: str) -> str:
    value = args.get(name, "").strip()
    if not value:
        message = f"MISSING_{name.upper()}"
        raise ValueError(message)
    return value


def _profile_slug(root: Path) -> str:
    slug = _PROFILE_SLUG_RE.sub("_", root.name).strip("_")
    return slug[:32] if slug else "profile"


def job_name_prefix(profile: ProfileState) -> str:
    return f"{JOB_PREFIX}_{_profile_slug(profile.root)}_"


def _redact_detail(detail: str) -> str:
    redacted = _PII_NAME_RE.sub("[redacted]", detail)
    return _NUMBER_RE.sub("[redacted]", redacted)
