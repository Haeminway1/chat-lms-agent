from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent import approvals
from chat_lms_agent.command_parser import build_parser
from chat_lms_agent.schedule import build_job_plan, redacted_run_log_record, scheduled_job
from chat_lms_agent.schedule_backend import FakeBackend
from chat_lms_agent.schedule_handlers import handle_schedule
from chat_lms_agent.state import ProfileState

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture

    from chat_lms_agent.state import JsonValue


def test_schedule_plan_write_action_builds_runnable_dry_run_argv_without_backend_write(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a write-action dry-run schedule plan request.
    backend = FakeBackend()
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")

    # When: plan is requested through the handler.
    exit_code = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "write-action",
            "--id",
            "record-class",
            "--from",
            str(payload_path),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=backend,
    )

    # Then: no backend mutation occurs and the private wrapper argv is tokenized.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["dry_run"] is True
    assert payload["job"]["kind"] == "write-action"
    assert payload["job"]["job_name"].startswith("ChatLMS_")
    assert backend.calls == []
    argv = _json_list(payload["action"]["argv"])
    assert argv[:6] == [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(tmp_path.resolve() / "codex-workspace" / "scripts" / "chat-lms-cli.ps1"),
    ]
    assert argv[-9:] == [
        "write-action",
        "plan",
        "--id",
        "record-class",
        "--from",
        str(payload_path.resolve()),
        "--profile-root",
        str(tmp_path.resolve()),
        "--json",
    ]


def test_schedule_plan_outbound_builds_runnable_dry_run_sync_argv(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: an outbound dry-run schedule plan request.
    db_path = tmp_path / "data" / "chat_lms.db"
    out_dir = tmp_path / "outbound"

    # When: plan is requested.
    exit_code = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "daily-management",
            "--database",
            str(db_path),
            "--date",
            "2026-06-27",
            "--out-dir",
            str(out_dir),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )

    # Then: the scheduled action is the existing sync surface without execute.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    argv = _json_list(payload["action"]["argv"])
    assert argv[-12:] == [
        "outbound",
        "daily-management",
        "sync",
        "--database",
        str(db_path.resolve()),
        "--out-dir",
        str(out_dir.resolve()),
        "--profile-root",
        str(tmp_path.resolve()),
        "--json",
        "--date",
        "2026-06-27",
    ]
    assert "--execute" not in argv


def test_schedule_plan_outbound_matches_target_specific_cli_contract(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: both outbound sync targets with their own supported argument shapes.
    db_path = tmp_path / "data" / "chat_lms.db"

    # When: daily-management is scheduled with a date range.
    dm_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "daily-management",
            "--database",
            str(db_path),
            "--from",
            "2026-06-01",
            "--to",
            "2026-06-30",
            "--out-dir",
            str(tmp_path / "dm-out"),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )
    dm_payload = _json_object(capsys.readouterr().out)
    # And: daily-lesson-homework is scheduled with class filtering.
    homework_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "daily-lesson-homework",
            "--database",
            str(db_path),
            "--date",
            "2026-06-27",
            "--classes",
            "EISS,EBSS",
            "--out-dir",
            str(tmp_path / "homework-out"),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )
    homework_payload = _json_object(capsys.readouterr().out)

    # Then: both scheduled command tails are accepted by the real top-level parser.
    assert [dm_exit, homework_exit] == [0, 0]
    _ = build_parser().parse_args(_scheduled_command_tail(dm_payload))
    _ = build_parser().parse_args(_scheduled_command_tail(homework_payload))
    dm_argv = _json_list(dm_payload["action"]["argv"])
    homework_argv = _json_list(homework_payload["action"]["argv"])
    assert "--classes" not in dm_argv
    assert "--from" not in homework_argv
    assert "--to" not in homework_argv


def test_schedule_register_requires_teacher_approval_before_backend_write(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: an unapproved schedule registration.
    backend = FakeBackend()
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")

    # When: register is requested.
    exit_code = handle_schedule(
        _write_action_register_args(tmp_path, payload_path),
        _repo_root(),
        backend=backend,
    )

    # Then: it creates an approval request and does not touch the backend.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 3
    assert payload["status"] == "NEEDS_APPROVAL"
    assert str(payload["plan_id"]).startswith("schedule:")
    assert backend.calls == []


def test_schedule_register_after_approval_is_idempotent_update(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: the teacher approved the exact schedule plan.
    backend = FakeBackend()
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")
    profile = ProfileState(root=tmp_path.resolve(), repo_root=_repo_root())
    plan = build_job_plan(
        profile,
        _repo_root(),
        kind="write-action",
        args={"id": "record-class", "from": str(payload_path)},
        trigger={"at": "08:30"},
    )
    _approve(profile, plan.plan_id)

    # When: the same job is registered twice.
    args = _write_action_register_args(tmp_path, payload_path)
    first_exit = handle_schedule(args, _repo_root(), backend=backend)
    first_payload = _json_object(capsys.readouterr().out)
    second_exit = handle_schedule(args, _repo_root(), backend=backend)
    second_payload = _json_object(capsys.readouterr().out)

    # Then: both calls upsert the same job id/name without duplication.
    assert [first_exit, second_exit] == [0, 0]
    assert first_payload["job"]["job_id"] == plan.job_id
    assert second_payload["job"]["job_id"] == plan.job_id
    assert [call["op"] for call in backend.calls] == ["upsert", "upsert"]
    assert backend.jobs.keys() == {plan.job_name}


def test_schedule_remove_rejects_names_outside_current_profile_namespace(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: one registered job owned by the current profile.
    profile_root = tmp_path / "teacher-a"
    backend = FakeBackend()
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")
    profile = ProfileState(root=profile_root.resolve(), repo_root=_repo_root())
    plan = build_job_plan(
        profile,
        _repo_root(),
        kind="write-action",
        args={"id": "record-class", "from": str(payload_path)},
        trigger={"at": "08:30"},
    )
    backend.upsert_job(scheduled_job(plan))
    backend.calls.clear()

    # When: remove is requested for another profile and for an unscoped name.
    other_exit = handle_schedule(
        [
            "schedule",
            "remove",
            "--profile-root",
            str(profile_root),
            "--name",
            "ChatLMS_teacher_b_abcdef123456",
            "--json",
        ],
        _repo_root(),
        backend=backend,
    )
    unsafe_exit = handle_schedule(
        [
            "schedule",
            "remove",
            "--profile-root",
            str(profile_root),
            "--name",
            r"..\ChatLMS_teacher_a_abcdef123456",
            "--json",
        ],
        _repo_root(),
        backend=backend,
    )
    own_exit = handle_schedule(
        [
            "schedule",
            "remove",
            "--profile-root",
            str(profile_root),
            "--name",
            plan.job_name,
            "--json",
        ],
        _repo_root(),
        backend=backend,
    )

    # Then: only the current profile's namespaced job reaches the backend.
    payloads = [_json_object(line) for line in capsys.readouterr().out.splitlines()]
    assert [other_exit, unsafe_exit, own_exit] == [2, 2, 0]
    assert payloads[0]["error_code"] == "UNSAFE_SCHEDULE_JOB_NAME"
    assert payloads[1]["error_code"] == "UNSAFE_SCHEDULE_JOB_NAME"
    assert payloads[2]["removed"] is True
    assert backend.calls == [{"op": "remove", "job_name": plan.job_name}]


def test_schedule_register_rejects_agent_self_approval_and_repo_profile_root(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: one normal temp profile and the public repo root.
    backend = FakeBackend()
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{}", encoding="utf-8")
    profile = ProfileState(root=tmp_path.resolve(), repo_root=_repo_root())
    plan = build_job_plan(
        profile,
        _repo_root(),
        kind="write-action",
        args={"id": "record-class", "from": str(payload_path)},
        trigger={"at": "08:30"},
    )
    code, payload = approvals.approve_request(
        profile,
        approvals.approval_id_for(plan.plan_id),
        approvals.AGENT_ACTOR,
    )

    # When: register runs without a real approval and with a repo-root profile.
    missing_approval_exit = handle_schedule(
        _write_action_register_args(tmp_path, payload_path),
        _repo_root(),
        backend=backend,
    )
    repo_root_exit = handle_schedule(
        [
            "schedule",
            "register",
            "--profile-root",
            str(_repo_root()),
            "--kind",
            "write-action",
            "--id",
            "record-class",
            "--from",
            str(payload_path),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=backend,
    )

    # Then: self-approval did not unlock it, and repo-root state is unsafe.
    outputs = [_json_object(line) for line in capsys.readouterr().out.splitlines()]
    assert code == 2
    assert payload["error_code"] == "SELF_APPROVAL_REJECTED"
    assert missing_approval_exit == 3
    assert outputs[0]["status"] == "NEEDS_APPROVAL"
    assert repo_root_exit == 4
    assert outputs[1]["status"] == "UNSAFE"
    assert backend.calls == []


def test_schedule_plan_rejects_free_shell_shortcut_and_execute_forms(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given/When: unsupported, shell-like, shortcut, or execute schedules are planned.
    shell_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "shell",
            "--command",
            "echo unsafe",
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )
    shortcut_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "shortcut",
            "--name",
            "daily",
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )
    execute_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "daily-management",
            "--database",
            str(tmp_path / "chat_lms.db"),
            "--date",
            "2026-06-27",
            "--out-dir",
            str(tmp_path / "outbound"),
            "--execute",
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )

    # Then: v1 allows no free shell, shortcut shell replay, or external execute path.
    assert shell_exit == 2
    assert shortcut_exit == 2
    assert execute_exit == 2
    payloads = [_json_object(line) for line in capsys.readouterr().out.splitlines()]
    assert payloads[0]["error_code"] == "UNSUPPORTED_SCHEDULE_KIND"
    assert payloads[1]["error_code"] == "SCHEDULE_SHORTCUT_DRY_RUN_UNSAFE"
    assert payloads[2]["error_code"] == "SCHEDULE_EXECUTE_UNSUPPORTED"


def test_schedule_plan_rejects_unknown_outbound_target_and_missing_required_args(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given/When: an outbound schedule references no real sync primitive or omits safe args.
    unknown_target_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "unknown",
            "--database",
            str(tmp_path / "chat_lms.db"),
            "--date",
            "2026-06-27",
            "--out-dir",
            str(tmp_path / "outbound"),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )
    missing_arg_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "daily-management",
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )
    dm_bad_arg_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "daily-management",
            "--database",
            str(tmp_path / "chat_lms.db"),
            "--date",
            "2026-06-27",
            "--classes",
            "EISS",
            "--out-dir",
            str(tmp_path / "outbound"),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )
    homework_bad_arg_exit = handle_schedule(
        [
            "schedule",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--kind",
            "outbound",
            "--target",
            "daily-lesson-homework",
            "--database",
            str(tmp_path / "chat_lms.db"),
            "--from",
            "2026-06-01",
            "--to",
            "2026-06-30",
            "--out-dir",
            str(tmp_path / "outbound"),
            "--at",
            "08:30",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )

    # Then: no nonexistent primitive or incomplete argv is accepted.
    assert unknown_target_exit == 2
    assert missing_arg_exit == 2
    assert dm_bad_arg_exit == 2
    assert homework_bad_arg_exit == 2
    payloads = [_json_object(line) for line in capsys.readouterr().out.splitlines()]
    assert payloads[0]["error_code"] == "UNSUPPORTED_OUTBOUND_TARGET"
    assert payloads[1]["error_code"] == "MISSING_DATABASE"
    assert payloads[2]["error_code"] == "UNSUPPORTED_OUTBOUND_ARG"
    assert payloads[3]["error_code"] == "UNSUPPORTED_OUTBOUND_ARG"


def test_schedule_argv_keeps_hostile_values_as_single_tokens(tmp_path: Path) -> None:
    # Given: a payload path containing shell metacharacters and unicode.
    hostile = 'name with spaces";&`%VAR% 한글.json'
    payload_path = tmp_path / hostile
    profile = ProfileState(root=tmp_path.resolve(), repo_root=_repo_root())

    # When: a plan is built.
    plan = build_job_plan(
        profile,
        _repo_root(),
        kind="write-action",
        args={"id": "record-class", "from": str(payload_path)},
        trigger={"at": "08:30"},
    )

    # Then: the hostile string remains one argv token, not shell text.
    resolved_hostile = str(payload_path.resolve())
    assert resolved_hostile in plan.action.argv
    assert plan.action.argv.count(resolved_hostile) == 1
    assert "--execute" not in plan.action.argv


def test_schedule_run_now_records_needs_human_without_external_write(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: no registered approved job exists.
    backend = FakeBackend()

    # When: run-now is requested for a missing job.
    exit_code = handle_schedule(
        [
            "schedule",
            "run-now",
            "--profile-root",
            str(tmp_path),
            "--id",
            "missing",
            "--json",
        ],
        _repo_root(),
        backend=backend,
    )

    # Then: no backend write occurs and a redacted needs_human run is recorded.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 3
    assert payload["status"] == "NEEDS_HUMAN"
    assert backend.calls == []
    runs_path = tmp_path / ".chat-lms-state" / "schedule" / "runs.jsonl"
    assert "missing" in runs_path.read_text(encoding="utf-8")


def test_schedule_run_log_redacts_scores_and_names() -> None:
    # Given: a run record with likely learner data.
    record = redacted_run_log_record(
        job_id="job",
        outcome="needs_human",
        detail="Fictional Ada scored 91 and needs review",
    )

    # Then: obvious names and scores are not stored verbatim in the detail field.
    detail = record["detail"]
    assert isinstance(detail, str)
    assert "Fictional Ada" not in detail
    assert "91" not in detail
    assert "[redacted]" in detail


def test_schedule_run_log_redacts_long_numeric_identifiers() -> None:
    # Given: a run record with phone-like and learner-id-like numeric data.
    record = redacted_run_log_record(
        job_id="job",
        outcome="needs_human",
        detail="student 12345 phone 01098765432 score 9999",
    )

    # Then: long numeric identifiers are not stored verbatim in the detail field.
    detail = record["detail"]
    assert isinstance(detail, str)
    assert "12345" not in detail
    assert "01098765432" not in detail
    assert "9999" not in detail
    assert detail.count("[redacted]") >= 3


def test_schedule_corrupt_run_log_never_raises(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a local run log with invalid UTF-8 bytes.
    runs_path = tmp_path / ".chat-lms-state" / "schedule" / "runs.jsonl"
    runs_path.parent.mkdir(parents=True)
    runs_path.write_bytes(b"\xff\xfe\xff")

    # When: runs are read and a new needs_human entry is appended.
    runs_exit = handle_schedule(
        ["schedule", "runs", "--profile-root", str(tmp_path), "--json"],
        _repo_root(),
        backend=FakeBackend(),
    )
    run_now_exit = handle_schedule(
        [
            "schedule",
            "run-now",
            "--profile-root",
            str(tmp_path),
            "--id",
            "missing",
            "--json",
        ],
        _repo_root(),
        backend=FakeBackend(),
    )

    # Then: both commands degrade safely instead of raising.
    payloads = [_json_object(line) for line in capsys.readouterr().out.splitlines()]
    assert [runs_exit, run_now_exit] == [0, 3]
    assert payloads[0]["runs"] == []
    assert payloads[1]["status"] == "NEEDS_HUMAN"
    assert "missing" in runs_path.read_text(encoding="utf-8")


def _write_action_register_args(tmp_path: Path, payload_path: Path) -> list[str]:
    return [
        "schedule",
        "register",
        "--profile-root",
        str(tmp_path),
        "--kind",
        "write-action",
        "--id",
        "record-class",
        "--from",
        str(payload_path),
        "--at",
        "08:30",
        "--json",
    ]


def _approve(profile: ProfileState, plan_id: str) -> None:
    request = approvals.ensure_approval_request(
        profile,
        plan_id=plan_id,
        operation="schedule register",
    )
    approval_id = request["approval_id"]
    assert isinstance(approval_id, str)
    code, payload = approvals.approve_request(profile, approval_id, "teacher")
    assert code == 0
    assert payload["approval_status"] == "APPROVED"


def _json_object(value: str | JsonValue) -> dict[str, JsonValue]:
    payload = json.loads(value) if isinstance(value, str) else value
    assert isinstance(payload, dict)
    return payload


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _scheduled_command_tail(payload: dict[str, JsonValue]) -> list[str]:
    argv = _json_list(payload["action"]["argv"])
    tokens = [str(token) for token in argv]
    wrapper_index = next(
        index for index, token in enumerate(tokens) if token.endswith("chat-lms-cli.ps1")
    )
    return tokens[wrapper_index + 1 :]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
