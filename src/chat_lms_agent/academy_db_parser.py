from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_academy_db_parser(subparsers: _SubparserGroup) -> None:
    academy_db = subparsers.add_parser("academy-db")
    academy_sub = academy_db.add_subparsers(dest="academy_db_command", required=True)
    spec = academy_sub.add_parser("spec")
    _ = spec.add_argument("--json", action="store_true")
    init = academy_sub.add_parser("init")
    _ = init.add_argument("--json", action="store_true")
    _add_profile_args(init)
    inspect = academy_sub.add_parser("inspect")
    _ = inspect.add_argument("--json", action="store_true")
    _add_profile_args(inspect)
    doctor = academy_sub.add_parser("doctor")
    _ = doctor.add_argument("--json", action="store_true")
    _add_profile_args(doctor)
    _add_schema_parser(academy_sub)
    _add_query_parser(academy_sub)
    _add_record_types_parser(academy_sub)
    _add_report_parser(academy_sub)
    _add_backup_parser(academy_sub)
    _add_migrate_parser(academy_sub)
    _add_restore_parser(academy_sub)
    _add_import_parser(academy_sub)


def _add_schema_parser(academy_sub: _SubparserGroup) -> None:
    schema = academy_sub.add_parser("schema")
    schema_sub = schema.add_subparsers(dest="academy_db_schema_command", required=True)
    show = schema_sub.add_parser("show")
    _ = show.add_argument("--json", action="store_true")
    _add_profile_args(show)


def _add_query_parser(academy_sub: _SubparserGroup) -> None:
    query = academy_sub.add_parser("query")
    query_sub = query.add_subparsers(dest="academy_db_query_command", required=True)
    query_list = query_sub.add_parser("list")
    _ = query_list.add_argument("--json", action="store_true")
    _add_profile_args(query_list)
    query_run = query_sub.add_parser("run")
    _ = query_run.add_argument("--name", required=True)
    _ = query_run.add_argument("--params")
    _ = query_run.add_argument("--json", action="store_true")
    _add_profile_args(query_run)


def _add_record_types_parser(academy_sub: _SubparserGroup) -> None:
    record_types = academy_sub.add_parser("record-types")
    record_types_sub = record_types.add_subparsers(
        dest="academy_db_record_types_command",
        required=True,
    )
    record_types_list = record_types_sub.add_parser("list")
    _ = record_types_list.add_argument("--json", action="store_true")
    _add_profile_args(record_types_list)


def _add_report_parser(academy_sub: _SubparserGroup) -> None:
    report = academy_sub.add_parser("report")
    report_sub = report.add_subparsers(dest="academy_db_report_command", required=True)
    report_build = report_sub.add_parser("build")
    _ = report_build.add_argument("--report", required=True)
    _ = report_build.add_argument("--json", action="store_true")
    _add_profile_args(report_build)


def _add_backup_parser(academy_sub: _SubparserGroup) -> None:
    backup = academy_sub.add_parser("backup")
    backup_sub = backup.add_subparsers(dest="academy_db_backup_command", required=True)
    backup_create = backup_sub.add_parser("create")
    _ = backup_create.add_argument("--json", action="store_true")
    _add_profile_args(backup_create)


def _add_migrate_parser(academy_sub: _SubparserGroup) -> None:
    migrate = academy_sub.add_parser("migrate")
    migrate_sub = migrate.add_subparsers(dest="academy_db_migrate_command", required=True)
    for name in ("plan", "apply"):
        migrate_cmd = migrate_sub.add_parser(name)
        _ = migrate_cmd.add_argument("--to", required=True)
        _ = migrate_cmd.add_argument("--json", action="store_true")
        _add_profile_args(migrate_cmd)


def _add_restore_parser(academy_sub: _SubparserGroup) -> None:
    restore = academy_sub.add_parser("restore")
    restore_sub = restore.add_subparsers(dest="academy_db_restore_command", required=True)
    restore_plan = restore_sub.add_parser("plan")
    _ = restore_plan.add_argument("--json", action="store_true")
    _add_profile_args(restore_plan)
    restore_apply = restore_sub.add_parser("apply")
    _ = restore_apply.add_argument("--plan-id")
    _ = restore_apply.add_argument("--json", action="store_true")
    _add_profile_args(restore_apply)


def _add_import_parser(academy_sub: _SubparserGroup) -> None:
    import_parser = academy_sub.add_parser("import")
    import_sub = import_parser.add_subparsers(dest="academy_db_import_command", required=True)
    plan = import_sub.add_parser("plan")
    _ = plan.add_argument("--from", dest="from_path", required=True)
    _ = plan.add_argument("--json", action="store_true")
    _add_profile_args(plan)
    apply = import_sub.add_parser("apply")
    _ = apply.add_argument("--from", dest="from_path", required=True)
    _ = apply.add_argument("--approval-id")
    _ = apply.add_argument("--json", action="store_true")
    _add_profile_args(apply)


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
