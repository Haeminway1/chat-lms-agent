from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, TypedDict

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

TODAY: Final = "2026-06-13"
OTHER_DAY: Final = "2026-06-12"
CASE_IDS: Final = [
    "learner-with-lesson-today",
    "new-learner-no-lessons",
    "multiple-learners-same-date",
    "unknown-student-typo",
    "import-apply-then-panel-populated",
]


class ScenarioCase(TypedDict):
    case_id: str
    mode: Literal["store", "import"]
    student: str
    lesson_date: str
    store: dict[str, JsonValue]
    summary: str
    entity_texts: tuple[str, ...]
    task_texts: tuple[str, ...]
    warnings: tuple[str, ...]
    forbidden_warnings: tuple[str, ...]


def scenario_case(case_id: str) -> ScenarioCase:
    for case in _scenario_cases():
        if case["case_id"] == case_id:
            return case
    message = f"missing scenario case: {case_id}"
    raise AssertionError(message)


def legacy_store_without_canonical_ids() -> dict[str, JsonValue]:
    return {
        "schema_version": "academy-v3",
        "classes": [
            {"class_id": "ga-legacy-class", "name": "가상 레거시반", "schedule": "Saturday 16:00"},
        ],
        "learners": [
            {
                "class_id": "ga-legacy-class",
                "learner_id": "ga-legacy-001",
                "level": "B1",
                "name": "가상학생 레거시",
            },
        ],
        "lessons": [
            {
                "date": TODAY,
                "homework": "Legacy homework",
                "learner_id": "ga-legacy-001",
                "materials": ["Legacy material"],
                "tasks": ["Legacy task"],
                "topic": "Legacy linked topic",
            },
        ],
    }


def _scenario_cases() -> tuple[ScenarioCase, ...]:
    return (
        {
            "case_id": "learner-with-lesson-today",
            "mode": "store",
            "student": "가상학생 하나",
            "lesson_date": TODAY,
            "store": _canonical_store(),
            "summary": "Past tense travel stories",
            "entity_texts": ("가상학생 하나", "A2", "가상 초등 A", "Unit 4 handout"),
            "task_texts": ("Review past tense", "Workbook p. 18"),
            "warnings": (),
            "forbidden_warnings": ("not found",),
        },
        {
            "case_id": "new-learner-no-lessons",
            "mode": "store",
            "student": "가상학생 신규",
            "lesson_date": TODAY,
            "store": _new_learner_store(),
            "summary": "등록된 수업 계획이 없습니다.",
            "entity_texts": ("가상학생 신규", "A1", "가상 초등 A"),
            "task_texts": (),
            "warnings": ("lesson record not found",),
            "forbidden_warnings": ("learner record not found",),
        },
        {
            "case_id": "multiple-learners-same-date",
            "mode": "store",
            "student": "가상학생 둘",
            "lesson_date": TODAY,
            "store": _canonical_store(),
            "summary": "Comparatives and superlatives",
            "entity_texts": ("가상학생 둘", "B1", "가상 초등 A", "Comparison chart"),
            "task_texts": ("Compare city pictures", "Record three comparison sentences"),
            "warnings": (),
            "forbidden_warnings": ("Past tense travel stories", "not found"),
        },
        {
            "case_id": "unknown-student-typo",
            "mode": "store",
            "student": "가상학생 오타",
            "lesson_date": TODAY,
            "store": _canonical_store(),
            "summary": "등록된 수업 계획이 없습니다.",
            "entity_texts": (),
            "task_texts": (),
            "warnings": ("learner record not found", "lesson record not found"),
            "forbidden_warnings": (),
        },
        {
            "case_id": "import-apply-then-panel-populated",
            "mode": "import",
            "student": "가상학생 하나",
            "lesson_date": TODAY,
            "store": {},
            "summary": "Past tense travel stories",
            "entity_texts": ("가상학생 하나", "A2", "가상 초등 A", "Unit 4 handout"),
            "task_texts": ("Review past tense", "Workbook p. 18"),
            "warnings": (),
            "forbidden_warnings": ("not found",),
        },
    )


def _canonical_store() -> dict[str, JsonValue]:
    return {
        "schema_version": "academy-v3",
        "classes": [{"id": "ga-class-alpha", "name": "가상 초등 A", "schedule": "Saturday 10:00"}],
        "learners": [
            {
                "class_id": "ga-class-alpha",
                "id": "ga-learner-001",
                "level": "A2",
                "name": "가상학생 하나",
            },
            {
                "class_id": "ga-class-alpha",
                "id": "ga-learner-002",
                "level": "B1",
                "name": "가상학생 둘",
            },
        ],
        "lessons": [
            {
                "date": TODAY,
                "homework": "Workbook p. 18",
                "learner_id": "ga-learner-001",
                "materials": ["Unit 4 handout", "Picture cards"],
                "tasks": ["Review past tense", "Role-play travel plans"],
                "topic": "Past tense travel stories",
            },
            {
                "date": TODAY,
                "homework": "Record three comparison sentences",
                "learner_id": "ga-learner-002",
                "materials": ["Comparison chart"],
                "tasks": ["Compare city pictures", "Correct comparative forms"],
                "topic": "Comparatives and superlatives",
            },
            {"date": OTHER_DAY, "learner_id": "ga-learner-001", "topic": "Older lesson"},
        ],
    }


def _new_learner_store() -> dict[str, JsonValue]:
    store = _canonical_store()
    learners = store["learners"]
    assert isinstance(learners, list)
    learners.append(
        {
            "class_id": "ga-class-alpha",
            "id": "ga-learner-new",
            "level": "A1",
            "name": "가상학생 신규",
        },
    )
    return store
