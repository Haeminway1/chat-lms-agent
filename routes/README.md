# Route Packs

Prompt routes are data, not code. Repo defaults live here as
`<route-id>.json`; the private profile adds or overrides packs under
`<profile-root>/.chat-lms-state/routes/` (profile wins by id).

Schema (`route-pack-v1`):

```json
{
  "schema_version": "route-pack-v1",
  "id": "example-route",
  "bucket": "trigger",
  "summary": "one-line purpose shown in hydration listings",
  "required_tokens": ["토큰1", "token2"],
  "first_command": "python -m chat_lms_agent ... --json",
  "then_command": "python -m chat_lms_agent ... --json",
  "fallback_command": "python -m chat_lms_agent doctor --json",
  "must_not": ["do not create a new HTML report for this request"],
  "time_budget_ms": 5000
}
```

Buckets:

- `always_inject` — the full route card rides along in every hydration.
- `listed_lazy` — only id and summary are listed; the body is read on demand.
- `trigger` — injected only when every `required_tokens` entry appears in the
  prompt.

One malformed pack file is skipped with a warning; it never aborts discovery
or poisons loaded routes. Packs must stay public-safe: no learner data, no
machine paths, no secrets.
