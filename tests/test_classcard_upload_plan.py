"""ClassCard planning-flow tests against a fully synthetic profile DB.

The predecessor repo's tests seeded from a real private database; these
rebuild the minimal ``tutoring_*`` schema with fake data instead, so the
behavior net ships in the public repo without any learner data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

_SYNTHETIC_SCHEMA = """
CREATE TABLE tutoring_students (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    public_id TEXT,
    attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE tutoring_lessons (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    lesson_date TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    progress TEXT NOT NULL DEFAULT '',
    homework TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE tutoring_lesson_words (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL,
    word_entry_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE tutoring_word_entries (
    id INTEGER PRIMARY KEY,
    canonical_headword TEXT NOT NULL
);
CREATE TABLE tutoring_word_senses (
    id INTEGER PRIMARY KEY,
    word_entry_id INTEGER NOT NULL,
    definition TEXT NOT NULL DEFAULT ''
);
CREATE TABLE tutoring_schedules (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    weekday INTEGER NOT NULL,
    day_label TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE classcard_upload_runs (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    student_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    tsv_path TEXT NOT NULL,
    checkpoint_path TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_WORDS = (
    ("apple", "사과"),
    ("river", "강"),
    ("bridge", "다리"),
    ("cloud", "구름"),
    ("school", "학교"),
    ("window", "창문"),
)


def _seed_profile_db(profile_root: Path) -> Path:
    db_path = profile_root / "data" / "chat_lms.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SYNTHETIC_SCHEMA)
    _ = conn.execute(
        "INSERT INTO tutoring_students(id, canonical_name, public_id) "
        "VALUES (1, '가상학생', 'ghost-1')",
    )
    _ = conn.execute(
        "INSERT INTO tutoring_lessons(id, student_id, lesson_date, subject) "
        "VALUES (10, 1, '2026-06-10', 'vocabulary')",
    )
    for index, (headword, meaning) in enumerate(_WORDS, start=1):
        _ = conn.execute(
            "INSERT INTO tutoring_word_entries(id, canonical_headword) VALUES (?, ?)",
            (index, headword),
        )
        _ = conn.execute(
            "INSERT INTO tutoring_word_senses(word_entry_id, definition) VALUES (?, ?)",
            (index, meaning),
        )
        _ = conn.execute(
            "INSERT INTO tutoring_lesson_words(lesson_id, word_entry_id) VALUES (10, ?)",
            (index,),
        )
    _ = conn.execute(
        "INSERT INTO tutoring_schedules(student_id, weekday, day_label) VALUES (1, 2, '수')",
    )
    conn.commit()
    conn.close()
    return db_path


def test_upload_prepare_plans_from_side_panel_words(tmp_path: Path) -> None:
    # Given: a synthetic profile DB shaped like the side-panel wordbook output.
    _ = _seed_profile_db(tmp_path)

    # When: the teacher prepares an upload (no --execute, no browser).
    result = _run_cli(
        "classcard",
        "upload",
        "--student",
        "가상학생",
        "--mode",
        "all",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: a plan, manifest, TSV parts, and a run-ledger row exist.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["classcard_status"] == "planned"
    assert payload["mode"] == "all"
    assert payload["parts"] >= 1
    checkpoint = Path(payload["checkpoint"])
    assert checkpoint.exists()
    manifest = json.loads(Path(payload["manifest"]).read_text(encoding="utf-8"))
    assert manifest["student"] == "가상학생"
    tsv_path = Path(str(manifest["parts"][0]["tsv_path"]))
    tsv_text = tsv_path.read_text(encoding="utf-8")
    assert "apple\t사과" in tsv_text
    conn = sqlite3.connect(tmp_path / "data" / "chat_lms.db")
    runs = conn.execute("SELECT status FROM classcard_upload_runs").fetchall()
    conn.close()
    assert runs == [("planned",)]


def test_upload_unknown_student_fails_loudly(tmp_path: Path) -> None:
    # Given: the synthetic DB without the requested student.
    _ = _seed_profile_db(tmp_path)

    # When/Then: a typo in the student name cannot silently upload anything.
    result = _run_cli(
        "classcard",
        "upload",
        "--student",
        "없는학생",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert result.returncode != 0


def test_upload_without_profile_db_reports_typed_error(tmp_path: Path) -> None:
    # Given: a profile with no data/chat_lms.db.
    # When: upload runs.
    result = _run_cli(
        "classcard",
        "upload",
        "--student",
        "가상학생",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the missing DB is named, with the --db override hinted.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "CLASSCARD_DB_NOT_FOUND"


def test_recover_reads_planned_checkpoint(tmp_path: Path) -> None:
    # Given: a planned run.
    _ = _seed_profile_db(tmp_path)
    prepared = _run_cli(
        "classcard",
        "upload",
        "--student",
        "가상학생",
        "--mode",
        "all",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert prepared.returncode == 0, prepared.stdout
    checkpoint = json.loads(prepared.stdout)["checkpoint"]

    # When: recover inspects the checkpoint without a browser.
    result = _run_cli(
        "classcard",
        "recover",
        "--checkpoint",
        checkpoint,
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the run state round-trips.
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["classcard_status"] in {"planned", "recovered"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        input="",
    )
