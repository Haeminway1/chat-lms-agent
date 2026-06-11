from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from chat_lms_agent.classcard_browser import (
    ClasscardAutomationError,
    ClasscardBrowserOptions,
    ClasscardSequenceResult,
    resume_start_index,
    upload_plan_with_playwright,
)
from chat_lms_agent.classcard_db import _previous_words, _student_id, connect, dump_json
from chat_lms_agent.classcard_plan import (
    ClasscardMode,
    UploadPlan,
    build_upload_plan,
    parse_classcard_mode,
)
from chat_lms_agent.classcard_verification import mark_recovery_required


@dataclass(frozen=True, slots=True)
class ClasscardRun:
    checkpoint_path: Path
    status: str
    tsv_path: Path


@dataclass(frozen=True, slots=True)
class PreparedClasscardUpload:
    checkpoint_path: Path
    manifest_path: Path
    plan: UploadPlan
    run_id: str
    status: str
    tsv_paths: tuple[Path, ...]


def dry_run_upload(
    db_path: str | Path,
    student: str,
    checkpoint_path: str | Path,
    *,
    simulate_interruption: bool = False,
) -> ClasscardRun:
    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    tsv_path = checkpoint.with_suffix(".tsv")
    with closing(connect(db_path)) as conn:
        student_id = _student_id(conn, student)
        words = _previous_words(conn, student_id)
        tsv_path.write_text(
            "\n".join(f"{word.headword}\t{word.meaning}" for word in words) + "\n",
            encoding="utf-8",
        )
        status = "interrupted" if simulate_interruption else "dry_run_ready"
        run_id = uuid4().hex
        payload = {"student": student, "classcard_flow": "copy_paste_tsv", "simulate_interruption": simulate_interruption}
        conn.execute(
            """
            INSERT INTO classcard_upload_runs(run_id, student_id, status, tsv_path, checkpoint_path, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, student_id, status, str(tsv_path), str(checkpoint), dump_json(payload)),
        )
        conn.commit()
        _write_checkpoint(checkpoint, status, tsv_path, db_path=Path(db_path), run_id=run_id)
    return ClasscardRun(checkpoint, status, tsv_path)


def recover_upload(checkpoint_path: str | Path) -> ClasscardRun:
    checkpoint = Path(checkpoint_path)
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    tsv_path = Path(str(payload.get("tsv_path") or payload.get("manifest_path")))
    db_path = payload.get("db_path")
    run_id = str(payload.get("run_id", ""))
    if isinstance(db_path, str) and db_path:
        with closing(connect(db_path)) as conn:
            conn.execute(
                "UPDATE classcard_upload_runs SET status = 'recovered', updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (run_id,),
            )
            conn.commit()
    if "manifest_path" in payload and "tsv_path" not in payload:
        payload["status"] = "recovered"
        checkpoint.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return ClasscardRun(checkpoint, "recovered", tsv_path)
    _write_checkpoint(checkpoint, "recovered", tsv_path, db_path=Path(str(db_path)) if db_path else None, run_id=run_id)
    return ClasscardRun(checkpoint, "recovered", tsv_path)


def prepare_upload(
    db_path: str | Path,
    student: str,
    checkpoint_path: str | Path,
    *,
    lesson_date: str | None = None,
    mode: ClasscardMode | None = None,
    span_days: int | None = None,
    out_dir: str | Path | None = None,
) -> PreparedClasscardUpload:
    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    plan = build_upload_plan(db_path, student, lesson_date=lesson_date, mode=mode, span_days=span_days)
    target_dir = Path(out_dir) if out_dir else checkpoint.with_suffix("")
    target_dir.mkdir(parents=True, exist_ok=True)
    tsv_paths = _write_part_tsvs(plan, target_dir)
    manifest_path = checkpoint.with_suffix(".manifest.json")
    run_id = uuid4().hex
    _write_manifest(manifest_path, plan, tsv_paths)
    _write_plan_checkpoint(checkpoint, "planned", plan, run_id, db_path=Path(db_path), manifest_path=manifest_path, tsv_paths=tsv_paths)
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO classcard_upload_runs(run_id, student_id, status, tsv_path, checkpoint_path, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                plan.student_id,
                "planned",
                str(manifest_path),
                str(checkpoint),
                dump_json({"student": plan.student_name, "mode": plan.mode.value, "part_count": len(plan.parts)}),
            ),
        )
        conn.commit()
    return PreparedClasscardUpload(checkpoint, manifest_path, plan, run_id, "planned", tsv_paths)


def execute_upload(
    db_path: str | Path,
    student: str,
    checkpoint_path: str | Path,
    *,
    lesson_date: str | None = None,
    mode: ClasscardMode | None = None,
    span_days: int | None = None,
    out_dir: str | Path | None = None,
    browser_options: ClasscardBrowserOptions | None = None,
) -> ClasscardSequenceResult:
    prepared = prepare_upload(
        db_path,
        student,
        checkpoint_path,
        lesson_date=lesson_date,
        mode=mode,
        span_days=span_days,
        out_dir=out_dir,
    )
    _update_run_status(db_path, prepared.run_id, "uploading")
    try:
        result = upload_plan_with_playwright(prepared.plan, prepared.checkpoint_path, options=browser_options)
    except ClasscardAutomationError as exc:
        mark_recovery_required(prepared.plan, prepared.checkpoint_path, db_path, prepared.run_id, str(exc))
        raise
    _update_run_status(db_path, prepared.run_id, result.status)
    return result


def resume_execute_upload(
    checkpoint_path: str | Path,
    *,
    browser_options: ClasscardBrowserOptions | None = None,
) -> ClasscardSequenceResult:
    checkpoint = Path(checkpoint_path)
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    db_path = Path(str(payload["db_path"]))
    run_id = str(payload["run_id"])
    plan = build_upload_plan(
        db_path,
        str(payload["student"]),
        lesson_date=str(payload["lesson_date"]),
        mode=parse_classcard_mode(str(payload["mode"])),
    )
    _update_run_status(db_path, run_id, "uploading")
    try:
        result = upload_plan_with_playwright(plan, checkpoint, options=browser_options, start_index=resume_start_index(checkpoint))
    except ClasscardAutomationError as exc:
        mark_recovery_required(plan, checkpoint, db_path, run_id, str(exc))
        raise
    _update_run_status(db_path, run_id, result.status)
    return result


def _write_checkpoint(checkpoint: Path, status: str, tsv_path: Path, *, db_path: Path | None, run_id: str) -> None:
    payload = {"status": status, "tsv_path": str(tsv_path), "run_id": run_id}
    if db_path is not None:
        payload["db_path"] = str(db_path)
    checkpoint.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_part_tsvs(plan: UploadPlan, target_dir: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for part in plan.parts:
        path = target_dir / f"{part.index + 1:02d}_{_safe_filename(part.title)}.tsv"
        path.write_text(part.tsv, encoding="utf-8")
        paths.append(path)
    return tuple(paths)


def _write_manifest(manifest_path: Path, plan: UploadPlan, tsv_paths: tuple[Path, ...]) -> None:
    payload = {
        "student": plan.student_name,
        "target_class_name": plan.target_class_name,
        "lesson_date": plan.lesson_date,
        "mode": plan.mode.value,
        "word_count": plan.word_count,
        "parts": [
            {
                "index": part.index,
                "label": part.label,
                "title": part.title,
                "assigned_date": part.assigned_date,
                "word_count": len(part.words),
                "tsv_path": str(tsv_paths[part.index]),
            }
            for part in plan.parts
        ],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_plan_checkpoint(
    checkpoint: Path,
    status: str,
    plan: UploadPlan,
    run_id: str,
    *,
    db_path: Path,
    manifest_path: Path,
    tsv_paths: tuple[Path, ...],
) -> None:
    payload = {
        "status": status,
        "run_id": run_id,
        "db_path": str(db_path),
        "student": plan.student_name,
        "target_class_name": plan.target_class_name,
        "lesson_date": plan.lesson_date,
        "mode": plan.mode.value,
        "manifest_path": str(manifest_path),
        "completed_indexes": [],
        "tsv_paths": [str(path) for path in tsv_paths],
    }
    checkpoint.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_run_status(db_path: str | Path, run_id: str, status: str) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            "UPDATE classcard_upload_runs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
            (status, run_id),
        )
        conn.commit()


def _safe_filename(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in value)
    return sanitized.strip("_") or "classcard"
