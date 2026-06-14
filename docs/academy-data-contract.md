# Academy Data Contract

The academy store is the data-binding source for academy imports and the
lesson panel. Importers may accept legacy field names, but persisted store data
must expose the canonical fields below so readers can render populated plans.

| Entity | Field | Required | Notes |
| --- | --- | --- | --- |
| `learners[]` | `id` | Yes | Canonical learner id. Import normalizes `learner_id` to this field when `id` is absent. |
| `learners[]` | `name` | Yes | Display name required by the lesson panel. Public fixtures use only `가상` names. |
| `learners[]` | `level` | No | Displayed in the lesson panel when present. |
| `learners[]` | `class_id` | No | Links the learner to `classes[].id`. |
| `classes[]` | `id` | Yes | Canonical class id. Import normalizes `class_id` to this field when `id` is absent. |
| `classes[]` | `name` | Yes | Display name for the class. |
| `classes[]` | `schedule` | No | Human-readable class schedule. |
| `lessons[]` | `date` | Yes | ISO date string used to select the lesson. |
| `lessons[]` | `student` | No | Learner display name link when available. |
| `lessons[]` | `learner_id` | No | Learner id link to `learners[].id`. |
| `lessons[]` | `topic` | No | Summary topic. |
| `lessons[]` | `materials[]` | No | Strings displayed as lesson materials. |
| `lessons[]` | `tasks[]` | No | Strings displayed as planned lesson tasks. |
| `lessons[]` | `homework` | No | Homework item appended to the task list. |

## Record Types

Record definitions use `record-type-v1` JSON files. Repository defaults live
under `assets/record-types/*.json`; profile overrides live under
`<profile-root>/.chat-lms-state/record-types/*.json`. The registry loads repo
files first and profile files second, so a profile file with the same `id`
replaces the repo default for that id. A malformed file is skipped with a typed
warning and does not stop discovery of other files.

Each file is a JSON object with:

| Field | Required | Notes |
| --- | --- | --- |
| `schema_version` | Yes | Must be `record-type-v1`. |
| `id` | Yes | Non-empty record type id. |
| `label` | Yes | Teacher-facing label string. |
| `target` | Yes | One of `learner|class|lesson`. Wave K1 ships learner-targeted defaults. |
| `summary` | No | Short description for humans and future UI surfaces. |
| `fields[]` | Yes | Ordered field definitions. |

Each `fields[]` item must include a non-empty `name` and a `type` from
`string|text|number|bool|date|enum`. `required` defaults to false when omitted.
`enum` fields require a non-empty `options` list.

Repo defaults:

| Record type | Target | Fields |
| --- | --- | --- |
| `attendance` | `learner` | `date` (`date`, required), `status` (`enum`, required, options `출석`, `결석`, `지각`, `조퇴`, `보강`), `note` (`text`, optional). |
| `journal` | `learner` | `date` (`date`, required), `homework_done` (`enum`, required, options `완료`, `부분완료`, `미완료`), `comment` (`text`, optional). |

If an import learner lacks `name` and no `display_name` can be derived, the
plan surfaces a typed `LEARNER_NAME_MISSING` warning with the affected learner
ids. Apply remains approval-gated; the warning tells the teacher that the
learner will need a display name before the panel can render a personalized
learner label.

## Records

Records are instances of a registered record type, stored in the academy
store under a top-level `records[]` list. Each record is an object with `type`
(a registered record-type id), `learner_id` (the canonical learner id resolved
at write time), and the type's field values. `classes`, `learners`, and
`lessons` are unchanged; `academy-db inspect` counts gain a `records` total.

CLI:

| Command | Notes |
| --- | --- |
| `academy-db record add --type <id> --learner <name\|id> --set <k=v> [--set …]` | Validates against the type's fields, then appends. `--from <values.json>` is an alternative to repeated `--set`. Routine local write, journaled via trace/audit. |
| `academy-db record list --type <id> --learner <name\|id> [--recent N]` | Returns the learner's records of that type, newest-first by `date`. `--recent N` caps the count. |

`record add` resolves the learner by `name`, `id`, or legacy `learner_id`. It
rejects an unknown type (`UNKNOWN_RECORD_TYPE`), an unresolvable learner
(`UNRESOLVABLE_LEARNER`), or values that fail the type's field validation
(`INVALID_RECORD`, with a typed error list) — nothing is written on rejection.

A request like "민준이 출결 보여줘" routes (route pack `learner_records`) to
`side-panel records open-plan --student <name> --type attendance`. The records
view reuses the existing lesson runtime: the installed server gains an
`/api/records-panel` endpoint, and the fixed viewer fetches it when opened with
`?view=records`. The payload is built by `records_panel_payload` from
`record list` data and passes `side-panel payload validate`, so the panel binds
records by rule — the agent never pastes record data into HTML.

## Onboarding

First-run onboarding builds each teacher's custom DB through a natural-language
interview the agent conducts, persisted only through deterministic CLIs — the
agent never hand-authors the store JSON. The private SessionStart hydrate adds
a first-run onboarding directive whenever the academy DB is missing.

| Step | Command |
| --- | --- |
| Define a custom thing to track (beyond the default `attendance`/`journal` types) | `academy-db record-types define --from <type.json>` writes a validated profile record type by id. |
| Seed classes and students | `academy-db import apply --from <roster.json>` (approval-gated; normalizes legacy ids; requires a learner `name` for display). |
| Review what is tracked | `academy-db record-types list`. |

`record-types define` validates the payload against `record-type-v1` and writes
it to `<profile-root>/.chat-lms-state/record-types/<id>.json`; an invalid
payload is rejected with a typed `error_code` and nothing is written. Roster
seeding reuses the existing approval-gated import flow rather than a separate
command.
