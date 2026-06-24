from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.classcard_live import summarize_live_sets

_SYNTHETIC_SCHEMA = """
CREATE TABLE tutoring_students (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL UNIQUE,
    attrs_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE tutoring_lessons (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    lesson_date TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    progress TEXT,
    homework TEXT,
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
    canonical_headword TEXT NOT NULL UNIQUE
);
CREATE TABLE tutoring_word_aliases (
    id INTEGER PRIMARY KEY,
    word_entry_id INTEGER NOT NULL,
    alias TEXT NOT NULL UNIQUE
);
CREATE TABLE tutoring_word_senses (
    id INTEGER PRIMARY KEY,
    word_entry_id INTEGER NOT NULL,
    definition TEXT NOT NULL DEFAULT ''
);
CREATE TABLE tutoring_quiz_sessions (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    lesson_id INTEGER,
    contract_id INTEGER,
    quiz_date TEXT NOT NULL,
    subject TEXT,
    score INTEGER,
    total INTEGER,
    pct REAL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE tutoring_quiz_items (
    id INTEGER PRIMARY KEY,
    quiz_session_id INTEGER NOT NULL,
    word_entry_id INTEGER NOT NULL,
    is_correct INTEGER NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(quiz_session_id, word_entry_id)
);
CREATE TABLE tutoring_student_word_state (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    word_entry_id INTEGER NOT NULL,
    wrong_count INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT,
    attrs_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, word_entry_id)
);
"""


def test_classcard_study_import_tracks_quiz_and_word_state(tmp_path: Path) -> None:
    db_path = _seed_profile_db(tmp_path)
    source = tmp_path / "classcard-result.json"
    source.write_text(
        json.dumps(
            {
                "items": [
                    {"word": "apple", "status": "memorized"},
                    {"word": "river", "status": "unmemorized"},
                    {"word": "bridge", "correct_count": 2, "wrong_count": 0},
                    {"word": "missing", "status": "wrong"},
                ],
            },
        ),
        encoding="utf-8",
    )

    result = _run_cli(
        "classcard",
        "study",
        "import",
        "--student",
        "fake-student",
        "--from",
        str(source),
        "--date",
        "2026-06-20",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["classcard_status"] == "study_imported"
    assert payload["items_seen"] == 4
    assert payload["items_imported"] == 3
    assert payload["items_skipped"] == 1
    assert payload["score"] == 3
    assert payload["total"] == 4
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT e.canonical_headword, s.correct_count, s.wrong_count, s.last_seen_at
        FROM tutoring_student_word_state s
        JOIN tutoring_word_entries e ON e.id = s.word_entry_id
        ORDER BY e.canonical_headword
        """,
    ).fetchall()
    session_count = conn.execute(
        "SELECT COUNT(*) FROM tutoring_quiz_sessions WHERE subject = 'classcard'",
    ).fetchone()[0]
    item_count = conn.execute("SELECT COUNT(*) FROM tutoring_quiz_items").fetchone()[0]
    conn.close()
    assert rows == [
        ("apple", 1, 0, "2026-06-20"),
        ("bridge", 2, 0, "2026-06-20"),
        ("river", 0, 1, "2026-06-20"),
    ]
    assert session_count == 1
    assert item_count == 3


def test_classcard_study_summary_and_due_words(tmp_path: Path) -> None:
    _ = _seed_profile_db(tmp_path)
    source = tmp_path / "classcard-result.json"
    source.write_text(
        json.dumps(
            {
                "items": [
                    {"word": "apple", "status": "memorized"},
                    {"word": "river", "status": "wrong"},
                    {"word": "bridge", "correct_count": 2, "wrong_count": 0},
                ],
            },
        ),
        encoding="utf-8",
    )
    imported = _run_cli(
        "classcard",
        "study",
        "import",
        "--student",
        "Fake Student",
        "--from",
        str(source),
        "--date",
        "2026-06-20",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert imported.returncode == 0, imported.stdout

    summary = _run_cli(
        "classcard",
        "study",
        "summary",
        "--student",
        "Fake Student",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    due = _run_cli(
        "classcard",
        "study",
        "due",
        "--student",
        "Fake Student",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    assert summary.returncode == 0, summary.stdout
    summary_payload = json.loads(summary.stdout)
    student = summary_payload["students"][0]
    assert student["status_counts"] == {
        "learning": 1,
        "mastered": 1,
        "new": 1,
        "review": 0,
        "weak": 1,
    }
    assert student["recent_sessions"][0]["quiz_date"] == "2026-06-20"
    assert due.returncode == 0, due.stdout
    due_payload = json.loads(due.stdout)
    assert [item["headword"] for item in due_payload["due_words"]] == ["river", "cloud"]


def test_classcard_registry_advertises_study_commands() -> None:
    result = _run_cli("agent-tools", "list", "--json")

    assert result.returncode == 0, result.stdout
    tools = {tool["id"]: tool for tool in json.loads(result.stdout)["tools"]}
    commands = "\n".join(tools["classcard"]["command_contract"]["commands"])
    assert "classcard study import" in commands
    assert "classcard study summary" in commands
    assert "classcard study due" in commands
    assert "classcard study live" in commands


def test_live_summary_weights_classcard_percentages() -> None:
    summary = summarize_live_sets(
        [
            {
                "card_count": 10,
                "mem_score": 200,
                "recall_score": 100,
                "spell_score": 100,
                "test_score": 100,
                "learn_completed": True,
            },
            {
                "card_count": 30,
                "mem_score": 50,
                "recall_score": 0,
                "spell_score": 0,
                "test_score": None,
                "learn_completed": False,
            },
        ],
    )

    assert summary["card_count"] == 40
    assert summary["mem_progress_pct"] == 87.5
    assert summary["mem_completion_pct"] == 62.5
    assert summary["recall_progress_pct"] == 25.0
    assert summary["spell_progress_pct"] == 25.0
    assert summary["test_average"] == 100.0
    assert summary["completed_sets"] == 1


def _seed_profile_db(profile_root: Path) -> Path:
    db_path = profile_root / "data" / "chat_lms.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SYNTHETIC_SCHEMA)
    _ = conn.execute(
        """
        INSERT INTO tutoring_students(id, public_id, canonical_name)
        VALUES (1, 'fake-student', 'Fake Student')
        """,
    )
    _ = conn.execute(
        """
        INSERT INTO tutoring_lessons(id, student_id, lesson_date, subject)
        VALUES (10, 1, '2026-06-20', 'vocabulary')
        """,
    )
    for index, (headword, meaning) in enumerate(
        (("apple", "fruit"), ("river", "water"), ("bridge", "crossing"), ("cloud", "sky")),
        start=1,
    ):
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
    conn.commit()
    conn.close()
    return db_path


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
