# Codex Desktop Transition-Ready Harness V3 Plan

## TL;DR

Chat LMS Agent remains a Codex Desktop harness today, but V3 makes the harness transition-ready for a later standalone desktop app or Web SaaS.

The important design rule:

```text
Codex Desktop adapter today
  -> reusable Chat LMS harness core
    -> private profile state, academy DB, memory, policy, audit, side-panel contracts
Future standalone desktop/Web SaaS adapter later
  -> same reusable Chat LMS harness core
```

V3 must not build a standalone model router or app server now. It must define the portable core contracts so a future host can reuse them.

## Opus 4.8 Plan Review Result

The plan was reviewed through `claude -p --model claude-opus-4-8`.

Verdict: conditionally approved.

Required corrections from review:

- Approval must name a human approval actor. The agent must never self-approve its own risky operation.
- Core statuses must stay host-neutral. CLI exit code `3` is a Codex/Desktop CLI adapter mapping for `NEEDS_APPROVAL`, not the portable core status itself.
- Trace, approval, and audit records need schema versions.
- Trace/audit redaction needs explicit tests for private profile logs, not only public repo scans.
- Append-only logs need retention/rotation policy.
- Approval, DB, memory, and journal writes need shared lock discipline.
- Approval expiration needs a concrete TTL.
- Import/apply needs backup verification and rollback behavior.
- Query params must be schema-validated and safely bound, never string-interpolated.

## Plain-Language Explanation

Right now Codex Desktop is the place where the AI thinks, reads, edits, and runs commands. Chat LMS Agent should not compete with Codex Desktop. It should make Codex much better at academy operations.

The problem V3 solves:

- The agent should not rebuild the academy DB workflow from scratch every session.
- The agent should not invent random HTML panels or one-off scripts.
- The agent should not perform risky class/student/report changes without a clear plan, approval, and record.
- The next session should immediately know what tools exist, what memory matters, what DB schema exists, and what work is pending.

The future-proofing part:

- Today, Codex Desktop triggers the hooks and runs the CLI.
- Later, a standalone desktop app or Web SaaS can trigger the same commands and read the same profile state.
- So the core data shape must be host-neutral: events, traces, approvals, memory, DB operations, and side-panel payloads must not depend on Codex-only internals.

## Current Baseline

Already completed in Harness V2:

- Full Codex hook lifecycle: `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PostCompact`, `Stop`.
- Reviewable memory workflow: `memory draft`, `memory apply-draft`, `memory verify`.
- `agent-tools` lifecycle CLI.
- `academy-db` foundation: `spec`, `init`, `query list/run`, `report build`, `backup create`, `migrate plan/apply`, `restore plan/apply`.
- Context, doctor, closeout, bootstrap integration.
- Public repo and private profile boundary enforcement.

Known gap:

- V2 is a strong Codex Desktop CLI harness, not yet a full operation-control layer.
- Some V2 DB contracts were planned but deferred: `inspect`, `schema show`, `import plan/apply`, `academy-db doctor`, query params.
- There is no host-neutral run journal, approval ledger, audit ledger, or memory compaction lifecycle yet.

## Golden Standard Reinterpretation

### Hermes Agent

Adopt:

- durable continuity;
- memory fencing;
- approval and audit discipline;
- safe runtime boundaries.

Do not adopt now:

- standalone provider router;
- full replacement agent loop;
- messaging gateway;
- network egress implementation.

### gajae-code

Adopt:

- `AgentRun`, `ToolCall`, `ToolResult` style trace concepts;
- event stream thinking;
- explicit tool execution records.

Do not adopt now:

- replacement LLM loop;
- app-owned streaming model runtime.

### lazycodex/OMO

Adopt:

- plugin/component lifecycle discipline;
- hooks and skills as installable surfaces;
- command discovery;
- evidence-first verification.

Do not adopt now:

- copying private plugin internals;
- coupling Chat LMS Agent to a specific external plugin implementation.

## Architecture Rule

Every new V3 feature must be split into:

1. Portable core contract
2. Codex Desktop adapter
3. Private profile storage
4. CLI surface
5. Tests and QA transcript

Example:

```text
Codex hook stdin payload
  -> Codex adapter converts to HarnessEvent
  -> portable policy/audit/memory/DB code handles it
  -> CLI emits stable JSON
  -> private profile state records sanitized trace
```

The future standalone app should be able to skip the Codex hook adapter and produce the same `HarnessEvent`.

## Default Decisions

- Trace coverage: V3 records every hook event and every state-changing or risky CLI operation. Pure read-only commands may emit JSON without journal writes.
- Approval artifact: approval is a persisted private profile record, not an interactive prompt.
- Approval statuses: `planned`, `dry_run`, `approved`, `applied`, `denied`, `expired`.
- Approval use: approval records are single-use for write operations.
- Approval actor: risky operations require a human approval actor. The agent may create an approval request, but must not approve its own request.
- Approval TTL: approval requests expire after 24 hours by default.
- Approval expiration is evaluated lazily when approvals are listed, shown, approved, or applied; V3 does not add a daemon or scheduler.
- Core status: approval-required operations return host-neutral status `NEEDS_APPROVAL`.
- CLI adapter mapping: `NEEDS_APPROVAL` maps to exit code `3` in the Codex Desktop CLI.
- External action intents: V3 records plan/audit payloads only. No real external adapters or external writes.
- Import sources: public repo imports are allowed only from explicit public-safe fixtures. Real imports must come from private profile paths.
- Query params: V3 supports JSON params files first. Inline JSON and repeated `--param key=value` are out of scope.
- Query safety: params are validated against named query schemas and safely bound to supported operations; params are never string-interpolated into executable query text.
- Memory archive: archived detail is excluded from default hydration; compact summaries remain hydratable.
- Golden standards: each standard must have source, pin status, adopted trait, local mapping, must-not-copy rule, and evidence.
- Log retention: trace/audit logs rotate or compact after 90 days or a configured size threshold, whichever comes first.
- State writes: approval, memory, and academy DB mutations use a shared profile-state lock.
- Trace and audit writes use append-only atomic write discipline and may also use the shared profile-state lock when a command writes multiple state files.

## Scope

### In Scope

- Host-neutral event envelope.
- Private profile run journal.
- Approval and audit ledger.
- Academy DB deferred commands.
- Memory compact/archive/session-summary drafts.
- Side-panel action policy bridge.
- Context, doctor, closeout, bootstrap V3 integration.
- Golden standard source pinning and terminology cleanup.

### Out Of Scope

- Standalone desktop app implementation.
- Web SaaS implementation.
- Provider-neutral model gateway.
- Product-owned LLM loop.
- Real external writes.
- Real learner data in public repo.
- Raw user-provided side-panel HTML/CSS committed as implementation.

## Target Command Surfaces

### New Or Expanded Commands

```text
python -m chat_lms_agent harness event normalize --from <payload.json> --json
python -m chat_lms_agent trace list --profile-root <root> --json
python -m chat_lms_agent trace show --profile-root <root> --id <trace-id> --json
python -m chat_lms_agent approval list --profile-root <root> --json
python -m chat_lms_agent approval show --profile-root <root> --id <approval-id> --json
python -m chat_lms_agent approval approve --profile-root <root> --id <approval-id> --json
python -m chat_lms_agent approval deny --profile-root <root> --id <approval-id> --json
python -m chat_lms_agent audit list --profile-root <root> --json
python -m chat_lms_agent academy-db inspect --profile-root <root> --json
python -m chat_lms_agent academy-db schema show --profile-root <root> --json
python -m chat_lms_agent academy-db query run --profile-root <root> --name <name> --params <params.json> --json
python -m chat_lms_agent academy-db import plan --profile-root <root> --from <source> --json
python -m chat_lms_agent academy-db import apply --profile-root <root> --plan-id <plan-id> --approval-id <approval-id> --json
python -m chat_lms_agent academy-db doctor --profile-root <root> --json
python -m chat_lms_agent memory compact --profile-root <root> --json
python -m chat_lms_agent memory archive --profile-root <root> --key <memory-key> --json
python -m chat_lms_agent session summarize --profile-root <root> --json
```

### Existing Commands Must Remain Compatible

```text
doctor
context hydrate
profile inspect
tool list/show/draft/activate/deprecate
agent-tools list/validate/scaffold/register/promote/deprecate/explain/doctor
memory upsert/list/verify/draft/apply-draft
session closeout
hook session-start/user-prompt-submit/post-tool-use/post-compact/stop
side-panel spec/block/view/payload
academy-db spec/init/query/report/backup/migrate/restore
bootstrap plan/apply/sync-runtime
```

## Storage Layout

All runtime files are private profile state:

```text
<profile-root>/.chat-lms-state/
  trace/
    trace-log.jsonl
  audit/
    audit-log.jsonl
  approvals/
    approvals.json
  academy/
    academy-store.json
    imports/
    reports/
    backups/
  memory.json
  memory-archive.json
```

Public repo must never contain these runtime artifacts.

## Trace Schema

Each trace event must contain:

```json
{
  "schema_version": "trace-v1",
  "trace_id": "trace_...",
  "parent_trace_id": null,
  "event_type": "hook|command|db_operation|memory_operation|approval_operation",
  "host": "codex_desktop",
  "command": ["academy-db", "import", "plan"],
  "profile_root": "<profile-root>",
  "status": "PASS|ERROR|BLOCKED|NEEDS_APPROVAL",
  "exit_code": 0,
  "started_at": "iso-8601",
  "ended_at": "iso-8601",
  "summary": "sanitized human-readable summary",
  "refs": ["audit_...", "approval_..."]
}
```

Trace must not store raw private paths, credentials, raw learner data, raw stdout, or raw prompts.

## Approval Schema

Each approval record must contain:

```json
{
  "schema_version": "approval-v1",
  "approval_id": "approval_...",
  "plan_id": "import_...",
  "operation": "academy-db.import.apply",
  "status": "planned|dry_run|approved|applied|denied|expired",
  "requested_by": "codex_desktop_agent",
  "approved_by": null,
  "single_use": true,
  "requires_backup": true,
  "expires_at": "iso-8601",
  "created_at": "iso-8601",
  "decided_at": null,
  "summary": "sanitized operation summary",
  "risk_level": "low|medium|high",
  "audit_refs": []
}
```

## Audit Schema

Each audit record must contain:

```json
{
  "schema_version": "audit-v1",
  "audit_id": "audit_...",
  "operation": "academy-db.import.apply",
  "actor": "codex_desktop_agent",
  "status": "planned|blocked|applied|denied|expired",
  "profile_root": "<profile-root>",
  "summary": "sanitized summary",
  "input_refs": [],
  "output_refs": [],
  "trace_id": "trace_..."
}
```

## Work Waves

### Wave 0. Documentation And Golden Standard Lock

Goal: fix conceptual drift before implementation.

Tasks:

- Fix mojibake in `docs/golden-standards.md`.
- Add source pin fields for lazycodex/OMO, gajae-code, Hermes Agent, OMC, and OMX.
- Add `docs/host-adapter-architecture.md`.
- Update terminology so Chat LMS Agent is defined as a Codex Desktop harness today and transition-ready core later.

Acceptance:

- `tests/test_docs_contract.py` verifies golden standard sections and pin fields.
- Docs explicitly say no standalone app/server is implemented in V3.
- Docs explicitly say future standalone host can reuse core contracts.

QA:

```powershell
uv run pytest tests/test_docs_contract.py -q
```

### Wave 1. Host-Neutral Harness Event Envelope

Goal: separate Codex hook payloads from portable harness events.

Tasks:

- Add a portable `HarnessEvent` model.
- Convert Codex hook stdin payloads into `HarnessEvent`.
- Add `harness event normalize`.
- Keep existing hook commands compatible.

Acceptance:

- Codex hook payload converts to `host: codex_desktop`.
- Malformed payload returns JSON contract error, no traceback.
- Future host field can be `standalone_desktop` or `web_saas` without changing DB/memory/policy code.

QA:

```powershell
uv run pytest tests/test_hook_payloads.py tests/test_hooks.py -q
uv run python -m chat_lms_agent harness event normalize --from tests/fixtures/hooks/session-start.json --json
```

### Wave 2. Private Profile Trace And Audit Journal

Goal: make Codex activity reviewable without leaking private data.

Tasks:

- Add append-only trace writer under private profile state.
- Add audit writer under private profile state.
- Add `trace list/show`.
- Add `audit list`.
- Trace every hook event and risky/state-changing operation.
- Do not trace pure read-only commands unless they are part of a risky workflow.

Acceptance:

- Trace files are never written in public repo.
- Trace output redacts profile root as `<profile-root>`.
- Trace records include host, event type, command, status, exit code, summary, refs.
- Concurrent writes use atomic append or lock-file discipline.
- Private trace/audit tests prove summaries do not store learner-like names, raw private paths, credentials, or raw stdout.
- Trace/audit rotation or compaction is tested with synthetic old records.

QA:

```powershell
uv run pytest tests/test_trace_journal.py tests/test_repo_privacy.py -q
```

### Wave 3. Approval And Dry-Run Policy Ledger

Goal: risky operations become plan-first and approval-gated.

Tasks:

- Add approval store and commands: `list`, `show`, `approve`, `deny`.
- Add policy function shared by DB and side-panel action intents.
- Return exit code `3` when approval is required.
- Make approval records single-use for write operations.
- External action intents remain plan/audit only.
- Store `requested_by` and `approved_by`; `approved_by` must not equal the requesting agent actor for risky operations.
- Expire pending approvals after the default TTL.
- Expiration is lazy-evaluated during `approval list/show/approve` and during any command that attempts to apply an approval.

Acceptance:

- `academy-db import apply` without approval exits `3`.
- Approved operation consumes the approval.
- Denied or expired approval cannot be applied.
- Agent-created approval cannot be self-approved by the same agent actor.
- Audit record is written for planned, denied, blocked, and applied outcomes.

QA:

```powershell
uv run pytest tests/test_approval_policy.py tests/test_audit_ledger.py -q
```

### Wave 4. Academy DB Deferred Contract Completion

Goal: finish the DB CLI pack as an agent-usable operations layer.

Tasks:

- Add `academy-db inspect`.
- Add `academy-db schema show`.
- Add `academy-db query run --params <params.json>`.
- Add `academy-db import plan`.
- Add `academy-db import apply`.
- Add `academy-db doctor`.
- Import `apply` requires private profile root, backup, plan id, and approval id.
- Public repo import sources are rejected unless they are explicit public-safe fixtures.
- Import `apply` verifies that backup creation succeeded and that the backup can be read before applying changes.
- Import `apply` writes rollback instructions into audit before mutating state.

Acceptance:

- Agent can inspect schema and query inventory without reading raw DB manually.
- Agent can run parameterized named queries through CLI.
- Import plan produces sanitized preview and approval requirement.
- Import apply cannot run from public repo state.
- Import apply cannot run without backup and approval.
- Import apply failure leaves either the old store intact or a restore-ready backup/audit record.
- Query params are validated against a named query params schema.

QA:

```powershell
uv run pytest tests/test_academy_db_cli.py tests/test_academy_db_imports.py tests/test_academy_db_params.py tests/test_academy_db_doctor.py -q
```

### Wave 5. Memory Compact, Archive, And Session Summary

Goal: keep memory useful across new Codex sessions without dumping everything.

Tasks:

- Add `memory compact`.
- Add `memory archive --key`.
- Add `session summarize`.
- Hydrate compact summaries by default.
- Exclude archived detail from default hydration.
- Closeout generates reviewable memory/session summary drafts, not silent memory writes.

Acceptance:

- Compact memory stays small and useful in `context hydrate`.
- Archived memory is still recoverable through explicit command but not injected by default.
- Session summary uses trace/audit refs instead of raw prompt text.
- Secrets and private paths are redacted before storage.

QA:

```powershell
uv run pytest tests/test_memory_compact_archive.py tests/test_session_summary.py tests/test_context_hydration_v2.py -q
```

### Wave 6. Side-Panel Action Policy Bridge

Goal: side-panel buttons remain visual/action intents, not uncontrolled writes.

Tasks:

- Connect side-panel action intent validation to approval/dry-run policy.
- Require `intent`, `requires_approval`, and `dry_run_default`.
- Add provenance links to sanitized DB query commands and audit ids.
- Keep user-owned HTML/CSS guidance as design reference only.

Acceptance:

- Side-panel payload with action button but no policy fails validation.
- Payload provenance can reference `academy-db query run --params`.
- No raw user HTML/CSS zip artifacts are committed.

QA:

```powershell
uv run pytest tests/test_side_panel_contract.py tests/test_side_panel_no_from_scratch.py -q
```

### Wave 7. Context, Doctor, Closeout, Bootstrap V3 Integration

Goal: new Codex sessions automatically know the V3 operating layer.

Tasks:

- `context hydrate` includes compact trace summary, pending approvals, academy DB schema/query inventory, memory compact summary, and side-panel action policy.
- `doctor` executes smoke checks for new commands using temp profiles.
- `session closeout` blocks unresolved approvals, unapplied DB plans, missing memory drafts, broken hooks, and unsafe runtime paths.
- `bootstrap sync-runtime` installs V3 hook/context wiring into private profile workspaces.

Acceptance:

- SessionStart injects concise V3 context.
- Stop/PostCompact block unfinished risky operations.
- Doctor reports `PASS`, `NEEDS_APPROVAL`, or `UNSAFE` with actionable repair guidance.
- Bootstrap does not perform imports, migrations, external writes, or destructive changes.

QA:

```powershell
uv run pytest tests/test_context_hydration_v3.py tests/test_doctor_v3.py tests/test_session_closeout_v3.py tests/test_bootstrap_v3.py -q
```

### Wave 8. Transition Adapter Contract

Goal: make the later standalone app migration cheap.

Tasks:

- Add a documented `HostAdapter` contract.
- Define supported hosts: `codex_desktop` now, `standalone_desktop` future, `web_saas` future.
- Add fixture events for future hosts without implementing the future app.
- Ensure core trace/policy/memory/DB tests do not import Codex-specific hook modules.

Acceptance:

- Portable core tests pass with fake `standalone_desktop` event fixtures.
- Codex adapter tests remain separate.
- No future host implementation is added.

QA:

```powershell
uv run pytest tests/test_host_adapter_contract.py tests/test_harness_event_envelope.py -q
```

### Wave 9. Final Verification

Goal: prove V3 is complete and transition-ready.

Automated gates:

```powershell
uv run pytest -q
uv run ruff check src tests
uv run basedpyright src
uv run pytest tests/test_repo_privacy.py -q
git diff --check
```

Manual CLI transcript gates:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name v3-codex-session-happy -Command "<full temp profile happy path>" -Evidence evidence/harness-v3/v3-codex-session-happy.txt
powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name v3-approval-block -Command "<approval required failure path>" -Evidence evidence/harness-v3/v3-approval-block.txt
powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name v3-db-import-private-boundary -Command "<import public/private boundary path>" -Evidence evidence/harness-v3/v3-db-import-private-boundary.txt
```

Final happy path must prove:

1. temp private profile is created;
2. SessionStart hydrates V3 context;
3. academy DB initializes;
4. schema is inspected;
5. parameterized query runs;
6. import plan creates approval requirement;
7. approval approve allows apply;
8. audit and trace records exist;
9. memory compact runs;
10. session closeout passes;
11. no public repo runtime artifact is created.

## Non-Developer Success Criteria

After V3, the agent should behave like this:

- It starts a new Codex session already knowing the approved academy tools.
- It knows where the private academy DB lives without exposing it publicly.
- It can inspect schema and run standard queries through commands instead of manually poking files.
- It creates a plan before risky DB changes.
- It asks for approval through a durable record before applying risky changes.
- It leaves an audit trail of what happened.
- It summarizes useful memory for the next session.
- It remains Codex Desktop-based today.
- It can later move into a standalone app because the core records and commands are not Codex-only.

## Failure Criteria

V3 fails if any of these happen:

- A DB/report/log/trace/audit/memory runtime file appears in public repo.
- A real learner record is added to public tests or docs.
- A risky DB import/apply runs without approval.
- A side-panel action can imply a write without intent and dry-run policy.
- Context hydration dumps raw private paths or oversized raw logs.
- Core DB/policy/memory logic depends directly on Codex hook payload shape.
- The plan creates a standalone app/server in V3.

## Recommended Implementation Order

1. Wave 0 docs and golden standard lock.
2. Wave 1 host-neutral event envelope.
3. Wave 2 trace/audit journal.
4. Wave 3 approval policy.
5. Wave 4 academy DB completion.
6. Wave 5 memory lifecycle.
7. Wave 6 side-panel policy bridge.
8. Wave 7 context/doctor/closeout/bootstrap.
9. Wave 8 transition adapter contract.
10. Wave 9 final verification.

This order keeps the current Codex Desktop use case working while steadily extracting the reusable core needed for a future standalone product.
