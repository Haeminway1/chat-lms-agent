# Academy Record Types Keystone Plan

Status: READY FOR IMPLEMENTATION (wave-gated, sequential K1→K4)
Author: dogfooding roadmap session 2026-06-13.
Executor: implement ONE wave per run; QA between waves; never start K(n+1)
inside a K(n) run.

## Purpose

Three of the teacher's wishlist items — attendance (출결), lesson journals
(일지), and "track an extra OO field" — are not three features. They are one
capability: **the teacher defines what to record, as data, and the harness
stores/validates/renders it through the existing deterministic pipeline.**
This plan builds that keystone, then the onboarding interview that fills it,
then the recent-data/attendance view that renders it. It deliberately reuses
the repo's proven "X-as-data" pattern (route packs, design systems): repo
defaults + per-profile overrides by id, profile wins, malformed file skipped
with a warning. The teacher's records bind to the viewer through the same
fixed-viewer + read-only API + design-lint/verify path the lesson panel
already uses, so the anti-hardcoding guarantee is inherited, not rebuilt.

## Verified Current State (2026-06-13)

- `src/chat_lms_agent/academy_db.py`: store is `{schema_version, classes[],
  learners[], lessons[]}` at `<profile>/.chat-lms-state/academy/
  academy-store.json`; `init_store`, `_read_store`/`_write_store`,
  `inspect_store` (counts), `schema_payload` (now carries the DF1 field
  contract per entity). Schema is fixed to those three entities;
  `plan_migration`/`apply_migration` are no-op stubs.
- The data-driven loader pattern to mirror exactly: `route_packs.py`
  (`load_route_packs` repo-then-profile, profile wins by id, one malformed
  file → warning, never aborts) and the design-system resolver
  (`side_panel_design_systems.py`).
- `src/chat_lms_agent/onboarding.py` only validates that an answers JSON is
  well-formed — no interview, no DB construction.
- Side-panel already registers contract views including `attendance_summary`
  and `learner_detail` (`side_panel.py:VIEWS`), and the lesson runtime gives
  a working fixed-viewer + `/api` + install/ensure/open-plan template
  (`side_panel_lesson*.py`, `assets/side-panel/`). Design lint + dual-fixture
  verify gates exist (`side_panel_design_lint.py`, the `design verify` CLI).
- Record/value validation precedent: `side_panel_validation.py` (typed error
  lists, exit codes).
- Gates: `uv run ruff check` (ALL), `uv run basedpyright` (all), `uv run
  pytest -q` (363 green at plan time); Linux CI ignores the two bootstrap
  suites.

## Domain Defaults (teacher-approved 2026-06-13; all profile-overridable)

- **attendance** statuses: `출석, 결석, 지각, 조퇴, 보강`.
- **journal (일지)** fields: `date`, `homework_done` (enum
  `완료/부분완료/미완료`), `comment` (text).
These ship as repo default record-type data files; any teacher replaces or
extends them by dropping a same-id file in their profile.

## Design Decisions

- **K-D1 — `record-type-v1` as data.** A record type file:
  ```json
  {
    "schema_version": "record-type-v1",
    "id": "attendance",
    "label": "출결",
    "target": "learner",
    "summary": "학생별 출결 기록",
    "fields": [
      {"name": "date",   "type": "date", "required": true,  "label": "날짜"},
      {"name": "status", "type": "enum", "required": true,  "label": "상태",
       "options": ["출석","결석","지각","조퇴","보강"]},
      {"name": "note",   "type": "text", "required": false, "label": "메모"}
    ]
  }
  ```
  Field `type` ∈ `string|text|number|bool|date|enum` (enum requires
  `options`). `target` ∈ `learner|class|lesson` (start with `learner`).
- **K-D2 — registry loader mirrors route packs.** `record_types.py`:
  `load_record_types(repo_root, profile)` loads `assets/record-types/*.json`
  then `<profile>/.chat-lms-state/record-types/*.json`, profile wins by id,
  one malformed file → warning string (never aborts). Repo ships
  `assets/record-types/attendance.json` and `assets/record-types/journal.json`
  with the approved defaults.
- **K-D3 — store extension, additive.** The academy store gains a top-level
  `records: []`; each record is `{"type": <id>, "learner_id": <id> or
  "learner": <name>, ...field values}`. `classes/learners/lessons` and every
  existing test stay byte-identical. `inspect_store` counts gain `records`.
- **K-D4 — record validation.** `record_validation.py`: a record must name a
  registered type, reference a resolvable learner, and satisfy that type's
  fields (required present, enum∈options, type coercion checks). Typed error
  list + exit codes mirroring `side_panel_validation.py`.
- **K-D5 — record CLI under the academy namespace.**
  - `academy-db record-types list --profile-root <root> --json` → id, label,
    source (repo|profile), target, fields.
  - `academy-db record add --type <id> --learner <name|id>
    --set <k=v> [--set …] --profile-root <root> --json` (or `--from
    values.json`): validates then appends; journaled via trace/audit; a
    routine local write (no approval gate — consistent with adding a lesson).
  - `academy-db record list --type <id> --learner <name|id> [--recent N]
    --profile-root <root> --json` → records newest-first (this powers the
    recent-data view).
- **K-D6 — onboarding interview persists to the registry (K3).** The agent
  conducts the natural-language interview (a skill/hydrate instruction drives
  it); the *product* side is deterministic CLI that persists outcomes:
  - `academy-db record-types define --from <answers.json> --profile-root
    <root> --json` writes a profile record-type file (validated against
    `record-type-v1`).
  - `academy-db seed --from <answers.json> --profile-root <root> --json`
    seeds classes/learners (reusing the import normalization + approval flow
    where it writes learner records).
  No conversational logic in the CLI; the harness stays a deterministic
  executor.
- **K-D7 — recent/attendance view rides the existing runtime (K4).** A new
  payload builder `side_panel_records_payload(profile, learner, type, recent)`
  returns a typed side-panel payload for a registered contract view
  (`attendance_summary` for attendance; a records timeline/list for others)
  built from `record list` data — empty/missing → graceful warning, never
  raises, includes `source_commands`, passes
  `side_panel_payload_validate`. It is served by the SAME fixed viewer +
  `/api` template family (extend `assets/side-panel/` rather than fork), so
  data binds by rule and design lint/verify apply. Route packs
  (`routes/learner-records.json`, `route-pack-v2`) add aliases like
  `출결, 출결 보여줘, 최근 기록, OO 최근, attendance` so "민준이 출결 보여줘"
  routes deterministically; NO_MATCH catalog picks it up otherwise.

## Wave K1 — record-type registry (data-driven)

- [ ] RED: loader tests mirroring `test_route_packs.py`: repo defaults
      (`attendance`, `journal`) load; profile file overrides repo by id;
      malformed file → warning, others still load; `record-type-v1` schema
      validation (bad field type, enum without options, missing id → typed
      errors).
- [ ] RED: `academy-db record-types list --json` contract test (id/label/
      source/target/fields; profile override visible).
- [ ] GREEN: `record_types.py` loader + `record-type-v1` validation,
      `assets/record-types/attendance.json` + `journal.json` (approved
      defaults), CLI wiring under the academy namespace.
- [ ] Docs: `docs/academy-data-contract.md` gains a record-types section.
- [ ] GATE: ruff + basedpyright + pytest (both runs); commit.

## Wave K2 — store records: add / list / validate

- [ ] RED: `record_validation` truth table (required missing, enum not in
      options, unknown type, unresolvable learner, good record → PASS).
- [ ] RED: `record add` then `record list` round-trip on a tmp profile
      (newest-first; `--recent N` caps; learner resolved by name and by id);
      store `classes/learners/lessons` untouched; `inspect_store` counts gain
      `records`.
- [ ] GREEN: store `records` extension, `record_validation.py`, `record
      add`/`record list` CLI, trace/audit journaling.
- [ ] Existing academy/import/lesson tests stay green unmodified.
- [ ] GATE: gates green; commit.

## Wave K3 — onboarding interview → custom DB

- [ ] RED: `record-types define --from answers.json` writes a valid profile
      record-type file and it then appears in `record-types list` as
      `source: profile`; invalid answers → typed error, nothing written.
- [ ] RED: `seed --from answers.json` seeds classes/learners (with the DF2
      name normalization + `LEARNER_NAME_MISSING` surfacing) on a tmp
      profile.
- [ ] GREEN: `record-types define` + `seed` CLIs; an onboarding skill /
      hydrate instruction block that tells the agent to run the interview
      (ask classes, learners, what to track) and persist via these CLIs —
      product code stays deterministic.
- [ ] Docs: onboarding flow in `docs/`; `plans/STATUS.md` update.
- [ ] GATE: gates green; commit.

## Wave K4 — recent-data / attendance view

- [ ] RED: `side_panel_records_payload` unit tests: populated attendance →
      `attendance_summary` payload with records newest-first + counts; empty →
      graceful warning; passes `side_panel_payload_validate`; includes
      `source_commands`.
- [ ] RED: `routes/learner-records.json` corpus test — `민준이 출결 보여줘`,
      `가상학생 최근 기록`, `attendance for …` route to the records route on
      BOTH hook and prompt-check; chitchat does not.
- [ ] RED: design lint PASS for the records viewer (panel + fullscreen);
      dual-fixture verify PASS (data binds, no hardcoding).
- [ ] GREEN: records payload builder, viewer/API extension in
      `assets/side-panel/`, `side-panel records open-plan/ensure-server`
      wiring (reuse `side_panel_runtime.py`), the route pack, doctor row for
      the records viewer lint/verify evidence.
- [ ] GATE: gates green (both runs); commit.

## Acceptance (end to end, tmp profile, after K4)

1. `record-types list` shows `attendance` + `journal` (repo) and any profile
   override wins by id.
2. `record add --type attendance --learner 가상민준 --set date=2026-06-13
   --set status=지각` then `record list --type attendance --learner 가상민준`
   returns it; an invalid status is rejected with a typed error.
3. Onboarding: `record-types define` + `seed` from a synthetic answers file
   builds a profile with a custom type and seeded learners.
4. `민준이 출결 보여줘` routes (both engines) → records viewer renders the
   attendance records, data bound by rule (design verify PASS), no
   hand-authored HTML.

## Non-goals

- Cron / scheduled wordbook generation (separate, deferred roadmap item).
- `class`/`lesson` targets beyond `learner` (start learner-only; extend later
  if needed).
- Real learner data; `가상` names only; no machine paths; no secrets.
- No change to routing-engine internals, design-system, or wordbook behavior
  beyond additive route packs / viewer assets.

## Execution Protocol

Binding: same as `plans/prompt-intent-routing-and-lesson-panel-plan.md`
Execution Protocol (TDD red→green, gates before every commit, hermetic
conftest, ISC003/NUL traps, public-safety `가상` only). Mirror the existing
data-driven loaders rather than inventing new patterns. ulw-loop launches
MUST redirect stdin (`< /dev/null`) and be startup-monitored.
