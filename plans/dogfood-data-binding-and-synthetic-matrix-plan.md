# Dogfood Data Binding + Synthetic Scenario Matrix Plan

Status: READY FOR IMPLEMENTATION (single wave; this is the "검증망 먼저" net)
Author: dogfooding session 2026-06-13.
Executor: implement TDD red→green; gates before every commit.

## Purpose

Dogfooding the shipped lesson-panel pipeline with *populated* synthetic data
exposed a real seam that 350 existing tests missed because they only ever
exercised the empty store. This plan pins the academy data-binding contract,
fixes the seam, and lays down a reproducible synthetic-scenario regression
matrix so the populated path can never silently regress again.

## Verified Finding (live, 2026-06-13)

Same student/date, two store shapes:

- Store shaped to what the payload reads (`learners[].name`/`id`,
  `lessons[].student/topic/materials/tasks/homework`,
  `classes[].id/name/schedule`) → panel renders fully, zero warnings.
- Store shaped like the official import format
  (`learners[].learner_id`, `classes[].class_id`, no `name`) →
  `lesson_panel_payload` returns warnings `learner record not found` +
  `lesson record not found`, empty plan.

Root cause: the field-name contract across import → store → payload was never
pinned. `src/chat_lms_agent/side_panel_lesson_payload.py:70-91` finds learners
by `name`/`id` and lessons by `student`/`learner`/`learner_id`;
`tests/fixtures/academy_db/public_safe_import.json` + the importer
(`academy_db_imports.py:_merge_import_payload`) carry `learner_id`/`class_id`
and NO `name`. A learner the teacher imports is therefore unrenderable (the
panel must display a `name` that import never provides).

## Design Decisions

- **DF1 — pin the academy entity field contract.** Canonical fields:
  - `learners[]`: `id` (string), `name` (string, REQUIRED for display),
    optional `level`, `class_id`.
  - `classes[]`: `id`, `name`, optional `schedule`.
  - `lessons[]`: `date`, a learner link (`student` = learner name, and/or
    `learner_id` = learner `id`), optional `topic`, `materials[]`, `tasks[]`,
    `homework`.
  Document this in `academy_db.schema_payload()` (add a `fields` block per
  entity) and a short table in `docs/` (architecture or a new
  `docs/academy-data-contract.md`). This is the single source of truth both
  the importer and the payload reader must obey.
- **DF2 — importer normalizes to the contract (back-compatible).** In
  `academy_db_imports._merge_import_payload` (or a normalization step it
  calls): map legacy `learner_id`→`id` and `class_id`→`id` when `id` absent;
  if a learner has neither `name` nor a derivable name, the import PLAN
  surfaces a typed warning (`LEARNER_NAME_MISSING`) listing affected ids so
  the teacher is told before apply — never silently store an unrenderable
  learner. Existing approval-gated flow unchanged; existing import tests stay
  green (extend, don't weaken).
- **DF3 — payload reader tolerant but contract-first.** `_find_learner`
  additionally matches `learner_id` so already-imported stores resolve; the
  canonical path remains `id`+`name`. No behavior change for the empty store
  or the already-passing populated-by-payload-shape case.
- **DF4 — synthetic public-safe dataset.** Add
  `tests/fixtures/academy_db/synthetic_academy.json` (public-safe, `가상`
  names only, `public_safe: true`) modeling a small 학원: 2 classes, ~4
  learners, lessons for today and other dates, with topics/materials/tasks/
  homework and varied levels. Reusable by tests and manual smoke.
- **DF5 — scenario regression matrix.** New
  `tests/test_lesson_panel_scenarios.py`, parametrized, asserting the panel
  payload for each dogfood scenario:
  1. learner with a lesson today → sections populated (summary topic,
     entity_list has Learner+Level+Class+Materials, task_list has tasks +
     homework), zero `not found` warnings.
  2. new learner, no lessons → learner found, lesson-not-found warning,
     graceful empty plan (no crash).
  3. multiple learners same date → the requested student's lesson is the one
     returned (no cross-contamination).
  4. name typo / unknown student → `learner record not found` warning,
     payload still valid and `side_panel_payload_validate`-clean.
  5. store written via the IMPORT path (apply `synthetic_academy.json` through
     `academy-db import apply` with approval) then read by the panel →
     populated (this is the regression that proves DF1-DF3 closed the seam).
- **DF6 — end-to-end populated render smoke (test or documented script).**
  Install assets, start the lesson server on an ephemeral port against the
  synthetic store, GET `/api/lesson-panel?student=<가상name>&date=<today>`,
  assert populated typed JSON; teardown. Linux-safe, skip-if-no-port-style
  guard consistent with the existing lesson runtime e2e.

## Non-goals
- No new product features (onboarding interview, dynamic schema/attendance,
  recent-data views, cron wordbook, custom journals) — those are a separate
  roadmap, tracked in `plans/STATUS.md` as gaps, NOT built here.
- No real learner data; `가상` names only; no machine paths; no secrets.
- No change to routing, design-system, or wordbook behavior.

## Checklist
- [x] RED: scenario matrix tests (DF5 1-5) + populated render (DF6) fail
      against current code (proving the seam).
- [x] GREEN: DF1 contract doc + `schema_payload` fields, DF2 importer
      normalization + `LEARNER_NAME_MISSING` plan warning, DF3 tolerant
      reader, DF4 synthetic fixture.
- [x] All five scenarios + the import-path regression pass.
- [x] Existing import/academy/lesson tests stay green unmodified.
- [x] GATE: `uv run ruff check` && `uv run basedpyright` && `uv run pytest -q`,
      plus `uv run pytest -q --ignore=tests/test_bootstrap.py
      --ignore=tests/test_bootstrap_v2.py`; commit.

## Acceptance
On a tmp profile: apply `synthetic_academy.json` via `academy-db import apply`
(with approval), `side-panel lesson install-assets`, `ensure-server`, then
`/api/lesson-panel?student=<가상name>` returns populated sections with zero
`not found` warnings — i.e. the exact path that is broken today now works.

## Execution Protocol
Binding: same as `plans/prompt-intent-routing-and-lesson-panel-plan.md`
Execution Protocol (TDD, gates before commit, hermetic conftest, ISC003/NUL
traps, public-safety `가상` only). ulw-loop launches MUST redirect stdin
(`< /dev/null`) and be startup-monitored.
