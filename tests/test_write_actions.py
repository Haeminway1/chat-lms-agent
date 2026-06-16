from __future__ import annotations

import json
from typing import TYPE_CHECKING

from chat_lms_agent.state import ProfileState
from chat_lms_agent.write_actions import (
    PlanError,
    WriteActionTemplate,
    WriteStep,
    compile_plan,
    load_write_actions,
    validate_template,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_load_write_actions_loads_repo_only_template(tmp_path: Path) -> None:
    # Given: one repo write-action template.
    repo_root = tmp_path / "repo"
    _write_template(repo_root / "write-actions" / "daily.json", _template_payload("daily"))

    # When: write actions load without a profile.
    templates, warnings = load_write_actions(repo_root, None)

    # Then: the repo template is returned without warnings.
    assert [template.template_id for template in templates] == ["daily"]
    assert templates[0].source == "repo"
    assert warnings == []


def test_load_write_actions_loads_profile_only_template(tmp_path: Path) -> None:
    # Given: one profile write-action template.
    repo_root = tmp_path / "repo"
    profile = ProfileState(root=tmp_path / "profile", repo_root=repo_root)
    _write_template(
        profile.root / ".chat-lms-state" / "write-actions" / "daily.json",
        _template_payload("daily"),
    )

    # When: write actions load from repo plus profile.
    templates, warnings = load_write_actions(repo_root, profile)

    # Then: the profile template is returned.
    assert [template.template_id for template in templates] == ["daily"]
    assert templates[0].source == "profile"
    assert warnings == []


def test_load_write_actions_profile_wins_by_id(tmp_path: Path) -> None:
    # Given: repo and profile templates with the same id.
    repo_root = tmp_path / "repo"
    profile = ProfileState(root=tmp_path / "profile", repo_root=repo_root)
    _write_template(
        repo_root / "write-actions" / "daily.json",
        _template_payload("daily", summary="repo summary"),
    )
    _write_template(
        profile.root / ".chat-lms-state" / "write-actions" / "daily.json",
        _template_payload("daily", summary="profile summary"),
    )

    # When: templates load.
    templates, warnings = load_write_actions(repo_root, profile)

    # Then: the profile template replaces the repo template.
    assert [template.template_id for template in templates] == ["daily"]
    assert templates[0].summary == "profile summary"
    assert templates[0].source == "profile"
    assert warnings == []


def test_load_write_actions_skips_malformed_missing_bom_and_bad_schema(
    tmp_path: Path,
) -> None:
    # Given: missing repo dir, profile templates with BOM, invalid JSON, and bad schema.
    repo_root = tmp_path / "repo"
    profile = ProfileState(root=tmp_path / "profile", repo_root=repo_root)
    actions_dir = profile.root / ".chat-lms-state" / "write-actions"
    actions_dir.mkdir(parents=True)
    _write_template(actions_dir / "bom.json", _template_payload("bom"), encoding="utf-8-sig")
    (actions_dir / "broken.json").write_text("{not json", encoding="utf-8")
    _write_template(
        actions_dir / "bad-schema.json",
        {**_template_payload("bad-schema"), "schema_version": "write-action-v0"},
    )

    # When: templates load.
    templates, warnings = load_write_actions(repo_root, profile)

    # Then: the BOM file loads and malformed files warn without aborting.
    assert [template.template_id for template in templates] == ["bom"]
    assert len(warnings) == 2
    assert any("INVALID_JSON" in warning for warning in warnings)
    assert any("UNSUPPORTED_SCHEMA_VERSION" in warning for warning in warnings)


def test_compile_plan_validates_required_type_enum_date_range_and_drops_unknown() -> None:
    # Given: a template with strict parameter schema.
    template = _template(
        param_schema={
            "student": {"type": "str", "required": True},
            "session_date": {"type": "date", "required": True},
            "attendance": {"type": "str", "enum": ["present", "absent"]},
            "score": {"type": "number", "min": 0, "max": 100},
        },
        steps=(
            WriteStep(
                step_id="insert_record",
                table="session_records",
                op="insert",
                match={},
                set={
                    "student_name": "$student",
                    "session_date": "$session_date",
                    "attendance": "$attendance",
                    "score": "$score",
                },
                depends_on=(),
                bind_result={},
            ),
        ),
    )

    # When: invalid and valid params compile.
    missing = compile_plan(template, {"session_date": "2026-06-16"})
    wrong_type = compile_plan(template, {"student": 7, "session_date": "2026-06-16"})
    bad_enum = compile_plan(
        template,
        {"student": "가상학생", "session_date": "2026-06-16", "attendance": "sleeping"},
    )
    bad_date = compile_plan(template, {"student": "가상학생", "session_date": "16-06-2026"})
    bad_range = compile_plan(
        template,
        {"student": "가상학생", "session_date": "2026-06-16", "score": 101},
    )
    valid = compile_plan(
        template,
        {
            "student": "가상학생",
            "session_date": "2026-06-16",
            "attendance": "present",
            "score": 95,
            "unknown": "ignored",
        },
    )

    # Then: expected failures are typed and unknown keys never become binds.
    assert isinstance(missing, PlanError)
    assert "MISSING_PARAM: student" in missing.errors
    assert isinstance(wrong_type, PlanError)
    assert "INVALID_PARAM_TYPE: student" in wrong_type.errors
    assert isinstance(bad_enum, PlanError)
    assert "INVALID_PARAM_ENUM: attendance" in bad_enum.errors
    assert isinstance(bad_date, PlanError)
    assert "INVALID_PARAM_DATE: session_date" in bad_date.errors
    assert isinstance(bad_range, PlanError)
    assert "INVALID_PARAM_RANGE: score" in bad_range.errors
    assert not isinstance(valid, PlanError)
    assert valid.steps[0].bind_order == ("가상학생", "2026-06-16", "present", 95)


def test_validate_template_rejects_off_whitelist_table_column_ref_op_and_bad_schema() -> None:
    # Given: several structurally invalid templates.
    bad_table = _template(
        steps=(
            WriteStep(
                step_id="bad_table",
                table="unsafe_table",
                op="insert",
                match={},
                set={"student_name": "$student"},
                depends_on=(),
                bind_result={},
            ),
        ),
    )
    bad_column = _template(
        steps=(
            WriteStep(
                step_id="bad_column",
                table="session_records",
                op="insert",
                match={},
                set={"unsafe_column": "$student"},
                depends_on=(),
                bind_result={},
            ),
        ),
    )
    bad_ref = _template(
        steps=(
            WriteStep(
                step_id="bad_ref",
                table="session_records",
                op="insert",
                match={},
                set={"student_name": "@missing_id"},
                depends_on=(),
                bind_result={},
            ),
        ),
    )
    bad_op = _template(
        steps=(
            WriteStep(
                step_id="bad_op",
                table="session_records",
                op="delete",
                match={},
                set={"student_name": "$student"},
                depends_on=(),
                bind_result={},
            ),
        ),
    )
    bad_schema = _template(param_schema={"student": {"type": "blob"}})

    # When: templates are validated.
    errors = [
        validate_template(bad_table),
        validate_template(bad_column),
        validate_template(bad_ref),
        validate_template(bad_op),
        validate_template(bad_schema),
    ]

    # Then: every invalid structure is rejected before execution.
    assert errors == [
        ["STEP_TABLE_NOT_WHITELISTED: bad_table.unsafe_table"],
        ["STEP_COLUMN_NOT_WHITELISTED: bad_column.session_records.unsafe_column"],
        ["UNKNOWN_CAPTURE_REF: bad_ref.@missing_id"],
        ["INVALID_STEP_OP: bad_op.delete"],
        ["INVALID_PARAM_SCHEMA_TYPE: student"],
    ]


def test_validate_template_rejects_invalid_capture_sources_per_operation() -> None:
    # Given: templates that request captures each operation cannot project.
    resolve_bad = _template(
        table_whitelist=("students",),
        columns={"students": ("id", "canonical_name")},
        steps=(
            WriteStep(
                step_id="resolve_student",
                table="students",
                op="resolve",
                match={"canonical_name": "$student"},
                set={},
                depends_on=(),
                bind_result={"student_id": "canonical_name"},
            ),
        ),
    )
    ensure_bad = _template(
        table_whitelist=("students",),
        columns={"students": ("id", "canonical_name")},
        steps=(
            WriteStep(
                step_id="ensure_student",
                table="students",
                op="ensure",
                match={"canonical_name": "$student"},
                set={"canonical_name": "$student"},
                depends_on=(),
                bind_result={"student_id": "lastrowid"},
            ),
        ),
    )
    insert_bad = _template(
        steps=(
            WriteStep(
                step_id="insert_record",
                table="session_records",
                op="insert",
                match={},
                set={"student_name": "$student"},
                depends_on=(),
                bind_result={"record_id": "id"},
            ),
        ),
    )
    update_bad = _template(
        steps=(
            WriteStep(
                step_id="update_record",
                table="session_records",
                op="update_stub",
                match={"student_name": "$student"},
                set={"attendance": "='present'"},
                depends_on=(),
                bind_result={"record_id": "id"},
            ),
        ),
    )

    # When: the invalid templates are validated.
    errors = [
        validate_template(resolve_bad),
        validate_template(ensure_bad),
        validate_template(insert_bad),
        validate_template(update_bad),
    ]

    # Then: every invalid capture source is rejected at registration.
    assert errors == [
        ["INVALID_CAPTURE_SOURCE: resolve_student.canonical_name"],
        ["INVALID_CAPTURE_SOURCE: ensure_student.lastrowid"],
        ["INVALID_CAPTURE_SOURCE: insert_record.id"],
        ["INVALID_CAPTURE_SOURCE: update_record.id"],
    ]


def test_validate_template_accepts_valid_capture_sources_per_operation() -> None:
    # Given: one valid capture form for each write operation.
    template = _template(
        table_whitelist=("students", "session_records"),
        columns={
            "students": ("id", "canonical_name"),
            "session_records": ("id", "student_name", "attendance"),
        },
        steps=(
            WriteStep(
                step_id="resolve_student",
                table="students",
                op="resolve",
                match={"canonical_name": "$student"},
                set={},
                depends_on=(),
                bind_result={"student_id": "id"},
            ),
            WriteStep(
                step_id="ensure_student",
                table="students",
                op="ensure",
                match={"canonical_name": "$student"},
                set={"canonical_name": "$student"},
                depends_on=(),
                bind_result={"ensured_student_id": "id"},
            ),
            WriteStep(
                step_id="insert_record",
                table="session_records",
                op="insert",
                match={},
                set={"student_name": "$student"},
                depends_on=(),
                bind_result={"record_id": "lastrowid"},
            ),
            WriteStep(
                step_id="update_record",
                table="session_records",
                op="update_stub",
                match={"id": "@record_id"},
                set={"attendance": "='present'"},
                depends_on=("insert_record",),
                bind_result={},
            ),
        ),
    )

    # When: the template is validated.
    errors = validate_template(template)

    # Then: all supported capture forms pass.
    assert errors == []


def test_compile_plan_rejects_invalid_template_without_sql() -> None:
    # Given: a template that references an off-whitelist column.
    template = _template(
        steps=(
            WriteStep(
                step_id="bad_column",
                table="session_records",
                op="insert",
                match={},
                set={"unsafe_column": "$student"},
                depends_on=(),
                bind_result={},
            ),
        ),
    )

    # When: compilation is attempted.
    result = compile_plan(template, {"student": "가상학생"})

    # Then: the compiler returns a typed error instead of SQL.
    assert isinstance(result, PlanError)
    assert result.code == "INVALID_TEMPLATE"


def test_compile_plan_never_interpolates_param_values_into_sql_text() -> None:
    # Given: a multi-op template with sensitive-looking fictional values.
    template = _template(
        table_whitelist=("classes", "sessions", "session_records"),
        columns={
            "classes": ("id", "class_code"),
            "sessions": ("id", "class_id", "session_date", "kind"),
            "session_records": ("id", "session_id", "student_name", "attendance"),
        },
        param_schema={
            "class_code": {"type": "str", "required": True},
            "session_date": {"type": "date", "required": True},
            "student": {"type": "str", "required": True},
        },
        steps=(
            WriteStep(
                step_id="resolve_class",
                table="classes",
                op="resolve",
                match={"class_code": "$class_code"},
                set={},
                depends_on=(),
                bind_result={"class_id": "id"},
            ),
            WriteStep(
                step_id="insert_session",
                table="sessions",
                op="insert",
                match={},
                set={
                    "class_id": "@class_id",
                    "session_date": "$session_date",
                    "kind": "='main'",
                },
                depends_on=("resolve_class",),
                bind_result={"session_id": "lastrowid"},
            ),
            WriteStep(
                step_id="update_record",
                table="session_records",
                op="update_stub",
                match={"session_id": "@session_id", "student_name": "$student"},
                set={"attendance": "='present'"},
                depends_on=("insert_session",),
                bind_result={},
            ),
        ),
    )
    values = {"class_code": "가상반-비밀", "session_date": "2026-06-16", "student": "가상학생"}

    # When: the plan compiles.
    plan = compile_plan(template, values)

    # Then: every SQL text contains only identifiers and placeholders, never values.
    assert not isinstance(plan, PlanError)
    for step in plan.steps:
        assert "?" in step.sql_text
        for value in values.values():
            assert value not in step.sql_text
    assert plan.steps[0].sql_text == "SELECT id FROM classes WHERE class_code = ?"
    assert plan.steps[1].sql_text == (
        "INSERT INTO sessions (class_id, session_date, kind) VALUES (?, ?, ?)"
    )
    assert plan.steps[2].sql_text == (
        "UPDATE session_records SET attendance = ? WHERE session_id = ? AND student_name = ?"
    )


def test_compile_plan_resolves_object_path_array_fanout_and_literal() -> None:
    # Given: a template with nested object, array fan-out, and fixed literal bindings.
    template = _template(
        param_schema={
            "classroom": {"type": "dict", "required": True},
            "students": {"type": "list", "required": True},
        },
        steps=(
            WriteStep(
                step_id="insert_records",
                table="session_records",
                op="insert",
                match={},
                set={
                    "student_name": "$students[].name",
                    "attendance": "='present'",
                    "note": "$classroom.note",
                },
                depends_on=(),
                bind_result={},
            ),
        ),
    )

    # When: compilation fans out over two fictional students.
    plan = compile_plan(
        template,
        {
            "classroom": {"note": "가상 메모"},
            "students": [{"name": "가상학생1"}, {"name": "가상학생2"}],
        },
    )

    # Then: one bound INSERT is emitted per array item.
    assert not isinstance(plan, PlanError)
    assert [step.bind_order for step in plan.steps] == [
        ("가상학생1", "present", "가상 메모"),
        ("가상학생2", "present", "가상 메모"),
    ]
    assert all(
        step.sql_text
        == "INSERT INTO session_records (student_name, attendance, note) VALUES (?, ?, ?)"
        for step in plan.steps
    )


def test_compile_plan_renders_ensure_as_insert_or_ignore_plus_select() -> None:
    # Given: an ensure step with a captured id.
    template = _template(
        steps=(
            WriteStep(
                step_id="ensure_test",
                table="tests",
                op="ensure",
                match={"name": "$test_name"},
                set={"name": "$test_name", "kind": "='quiz'"},
                depends_on=(),
                bind_result={"test_id": "id"},
            ),
        ),
        table_whitelist=("tests",),
        columns={"tests": ("id", "name", "kind")},
        param_schema={"test_name": {"type": "str", "required": True}},
    )

    # When: the plan compiles.
    plan = compile_plan(template, {"test_name": "가상퀴즈"})

    # Then: ensure emits fixed insert-or-ignore and select statement shapes.
    assert not isinstance(plan, PlanError)
    assert [step.sql_text for step in plan.steps] == [
        "INSERT OR IGNORE INTO tests (name, kind) VALUES (?, ?)",
        "SELECT id FROM tests WHERE name = ?",
    ]
    assert [step.bind_order for step in plan.steps] == [
        ("가상퀴즈", "quiz"),
        ("가상퀴즈",),
    ]
    assert plan.steps[1].captures == {"test_id": "id"}


def _template_payload(template_id: str, *, summary: str = "가상 쓰기") -> dict[str, object]:
    return {
        "schema_version": "write-action-v1",
        "id": template_id,
        "summary": summary,
        "route_id": "daily-route",
        "table_whitelist": ["session_records"],
        "columns": {
            "session_records": [
                "id",
                "student_name",
                "session_date",
                "attendance",
                "score",
                "note",
            ],
        },
        "param_schema": {
            "student": {"type": "str", "required": True},
        },
        "steps": [
            {
                "step_id": "insert_record",
                "table": "session_records",
                "op": "insert",
                "set": {"student_name": "$student"},
            },
        ],
    }


def _template(
    *,
    table_whitelist: tuple[str, ...] = ("session_records",),
    columns: dict[str, tuple[str, ...]] | None = None,
    param_schema: dict[str, dict[str, object]] | None = None,
    steps: tuple[WriteStep, ...] = (),
) -> WriteActionTemplate:
    return WriteActionTemplate(
        template_id="daily",
        schema_version="write-action-v1",
        summary="가상 쓰기",
        route_id="daily-route",
        table_whitelist=table_whitelist,
        columns=columns
        if columns is not None
        else {
            "session_records": (
                "id",
                "student_name",
                "session_date",
                "attendance",
                "score",
                "note",
            ),
        },
        param_schema=param_schema if param_schema is not None else {"student": {"type": "str"}},
        steps=steps,
        source="repo",
    )


def _write_template(path: Path, payload: dict[str, object], *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding=encoding)
