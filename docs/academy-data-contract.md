# Academy Data Contract

The academy store is the data-binding source for academy imports and panel
readers. Importers may accept legacy field names, but persisted store data
must expose the canonical fields below so readers can render populated plans.

| Entity | Field | Required | Notes |
| --- | --- | --- | --- |
| `learners[]` | `id` | Yes | Canonical learner id. Import normalizes `learner_id` to this field when `id` is absent. |
| `learners[]` | `name` | Yes | Display name required by panel readers. Public fixtures use only `가상` names. |
| `learners[]` | `level` | No | Displayed by panel readers when present. |
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

## Import Safety

If an import learner lacks `name` and no `display_name` can be derived, the
plan surfaces a typed `LEARNER_NAME_MISSING` warning with the affected learner
ids. Apply remains approval-gated; the warning tells the teacher that the
learner will need a display name before a reader can render a personalized
learner label.
