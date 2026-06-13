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
