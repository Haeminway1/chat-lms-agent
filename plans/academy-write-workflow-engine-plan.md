# Generic Write-Workflow Engine Plan (record-class = first template)

Status: **DESIGN — awaiting teacher approval before implementation.** Produced by the
2026-06-16 latency-diagnosis → architecture-design sessions (3 independent
approaches, adversarial safety judging, synthesis). Honors the global rule:
design + test plan + success/failure criteria documented BEFORE coding.

## Why (the problem this fixes)

Daily class-record entry (기입: 출석/숙제/점수/진도) takes 2–4 min per class because
the harness has **no DB-write executor**. The `academy-db` CLI is read-only
(named queries `learner-count`/`class-count` only); the `agent-tools` `academy-db`
entry is `status:"planned"` — a placeholder never built. So the agent hand-writes a
multi-table raw-SQL transaction against the private `data/chat_lms.db` every class.
Verified from the real 2026-06-15 Codex rollout: **95–97 % of each op's wall time is
LLM improvisation**; the actual DB write was 0.46 s. (Diagnosis detail: this repo's
sibling plan + memory `academy-data-entry-no-write-command`.)

Decided direction (teacher): the harness is a **meta-framework that grows by
registering gated capabilities as DATA bottoming out in ONE generic core executor** —
not a hardcoded `record-class` command. `record-class` is the FIRST registered
template that proves the pattern; future writes (enroll, adjust-scores, reschedule)
are pure data with zero new core Python.

## Chosen architecture

**Approach A (generic data-driven write engine + `write-action-v1` declarative
upsert-plan template) hardened with B/C safety grafts.** Judge scores: A
harness-fit/turn-reduction/zero-dep/testability/extensibility all 5 (effort the only
weak axis); B safest-by-construction but less data-driven; C same vision, lower safety.
Synthesis = A's spine + B/C's structural safety fixes.

### Two new core modules (`src/chat_lms_agent/`, stdlib `json`+`sqlite3` only, host-token-free)

1. **`write_actions.py`** — template data layer + loader + plan **compiler** (pure, no
   real-DB I/O), mirroring `route_packs.py` in shape.
   - `WriteActionTemplate(template_id, schema_version, summary, route_id,
     table_whitelist, columns{table→allowed-cols}, param_schema, steps, source)`.
   - `WriteStep` = a **narrow four-op vocabulary, NO `sql` field, no joins/conditionals**:
     `resolve` (lookup one id by a UNIQUE column), `insert` (one parameterized INSERT,
     capture `lastrowid`), `ensure` (UPSERT-by-unique-key: INSERT OR IGNORE → SELECT id),
     `update_stub` (**trigger-aware UPDATE-ONLY** of child rows by parent+match key —
     structurally cannot blind-INSERT over trigger stubs).
   - `load_write_actions(repo_root, profile)` → repo `write-actions/` then profile
     `.chat-lms-state/write-actions/`, profile wins by id, tolerant skip-with-warning.
   - `compile_plan(template, params)` → lowers each step to `(sql_text, bind_order,
     captures)` where **`sql_text` is harness-authored from ONLY whitelisted table+column
     identifiers**; every runtime value binds as a `?` parameter — params are NEVER
     interpolated into SQL text. This is the single security-critical path.
   - `validate_template(...)` → structural check run at **registration time** (every
     step table/column in the whitelist, every `@ref` produced by a prior step, op is
     one of the four) so a bad template is rejected before it can ever be replayed.

2. **`write_engine.py`** — the ONE generic executor (only module touching the real DB;
   injectable `connect` seam = `ConnectFn` Protocol over `classcard_db.connect`).
   `run_write_action(profile, template, params, *, db_path, connect=…, now=…)`:
   1. **pin db_path** — non-test mode MUST resolve under `profile.root/data`; outside-profile
      or under-repo → exit 4 UNSAFE, no connect (closes the unconstrained `--db` seam).
   2. **binary-safe backup** — `PRAGMA wal_checkpoint(TRUNCATE)` then
      `shutil.copyfile` (precedent: `side_panel_design_promotion._backup_existing_viewer`,
      **NOT** `academy_db.create_backup` which `read_text/write_text`s and corrupts a
      binary DB). Backup target == write target (same pinned path).
   3. `compile_plan`; resolve lookups via parameterized SELECT (miss → exit 2, no write).
   4. **one explicit transaction** (`isolation_level` not None) across all steps;
      `PRAGMA table_info` belt-and-suspenders column check; any error → ROLLBACK, exit 2
      with failing `step_id`, backup retained.
   5. COMMIT → `journal.write_audit/write_trace` with **ID/count-only** details.

### Data + binding

- **Repo default templates** → new public `write-actions/` dir (identifiers + bindings
  only; passes `test_repo_privacy.py`). **Profile templates + ALL filled payloads +
  compiled plans + backups** → `.chat-lms-state/write-actions/{,payloads/,backups/}` —
  real learner data NEVER touches the repo (same containment as approvals/imports;
  `pre_tool_gate` already denies an agent write of profile-referencing content into the repo tree).
- **NL binding (no new routing mechanism):** repo `routes/record-class.json`
  (route-pack-v2, trigger on `기입` etc.) `first_command`=`write-action plan …`,
  `then_command`=`write-action apply …`; profile shortcut `기입.json` runs apply.

### Trust boundary (front-loaded at registration; replay is low-risk)

Registration rides the existing `agent_tool_lifecycle.py` draft→registered→active flow
(5 required contracts; `validate_template` at register time; promote needs `--evidence`
+ teacher approval). The **real gate is `approval_handlers._handle_approve`'s
`stream.isatty()` + typed-id echo** — the agent has no TTY. `--actor` is demoted to
audit metadata only (the `approvals.py` actor-string self-rejection is documented-
spoofable and must NOT be relied on). Per-replay approval is NEVER auto/blanket-enabled.

Exit codes: 0 PASS / 2 ERROR / 3 NEEDS_APPROVAL / 4 UNSAFE / 5 BLOCKED.

## record-class — the first `write-action-v1` template

Ported from legacy `hls_lite` `agent_actions.action_type='record_class'`. Proves all
four ops with ZERO record-class-specific Python.

Payload (filled copy lives only in profile, passed via `--from`):
`{class_code, session_date, session_kind∈{main,makeup,test}=main, subject?, progress?,
homework?, students:[{name, attendance∈{present,absent,late,excused}, homework_score 0..100?,
note?}], tests:[{name, kind, results:[{name, correct, total}]}]?}`

Trigger-aware plan: `resolve class_id` → `insert sessions` (fires
`trg_sessions_auto_student_session_records` which auto-stubs `student_session_records`
from active enrollments) → per student `resolve student_id` + **`update_stub`**
(`source='teacher_prompt'`, attendance, homework_score) — **UPDATE-only makes the
Monday session-579 `attendance=NULL` bug unrepresentable**; a make-up student with no
stub is the documented explicit-insert exception → `ensure tests` then `insert
test_results` (pct derived). Audit row matches legacy `{records, session_id,
test_results}` shape, ID/count-only.

**Result:** a daily 기입 = LLM fills the payload JSON (one constrained turn) → one
`plan` dry-run (0 writes, predicts row counts) → one deterministic `apply`. The model
composes zero SQL and never names tables/columns/step order.

## Test plan (hermetic; injected `connect`/`now` seams; NO real DB / subprocess)

- **Compiler/loader (pure):** profile-wins loader, malformed skip, schema-version gate;
  param validation (required/type/enum/date/range); **whitelist enforcement** (off-list
  table/column/`@ref`/op → error; assert no param value appears in `sql_text`);
  `validate_template` at register time; `$arr[].field` fan-out / `='literal'`.
- **Engine (real trigger in DDL fixture):** trigger UPDATE-not-INSERT + no duplicate
  (session-579 regression); attendance-NULL repair; make-up no-stub insert; mid-txn error
  → ROLLBACK leaves DB byte-identical + names step_id; **backup `PRAGMA integrity_check
  == ok`** + WAL checkpoint + target==write-target; `--db` outside profile/under repo →
  exit 4 no-connect; lookup miss → exit 2 no-write; tests-before-test_results ordering;
  multi-class/student fan-out; isolation_level not None.
- **Gate:** scaffold needs 5 contracts; promote w/o `--evidence` blocked; non-active replay
  → NEEDS_APPROVAL(3); non-tty approve → BLOCKED(5); typed-id mismatch → BLOCKED(5);
  spoofed `--actor` cannot register; single-use consume.
- **Privacy/host:** audit/trace files contain no learner name/score; repo template passes
  `test_repo_privacy.py`; filled payload→repo path denied by `pre_tool_gate`; both modules
  pass `test_host_independence.py`. Full suite (existing ~199 + new) green; ruff/basedpyright clean.

## Success criteria

1. 기입 collapses to 1 LLM turn + `plan` dry-run + `apply`; model writes zero SQL.
2. record-class ships as DATA only (template + route + shortcut), no record-class Python.
3. Trigger stubs UPDATED, no duplicate row; session-579 bug structurally impossible (test-proven).
4. No arbitrary SQL: no `sql` field; identifiers from whitelist only; values are `?` (test-proven).
5. Backup is integrity-checked sqlite of the same pinned path; mid-txn failure rolls back.
6. `--db`/default resolves only under `profile.root/data`; else exit 4 before connect.
7. Registration gated by real isatty()+typed-id; `--actor` audit-only; non-active replay → 3.
8. Ledgers are ID/count-only — no learner names/scores anywhere.
9. A SECOND write action = new JSON template + route/shortcut + tests, zero core Python.
10. Exit-code contract exact; both modules host-token-free + zero-dep; suite green.

## Failure criteria

1. Engine can emit any interpolated identifier/value, or a template can reach off-whitelist.
2. record-class blind-INSERTs into `student_session_records` (re-introduces NULL/dupes).
3. Backup uses text-copy / non-binary-safe path, or target≠write-target, or no clean restore.
4. `--db` can aim writes/backup outside `profile.root/data` without exit 4.
5. Trust rests on `--actor` string rather than isatty+typed-id, or per-replay approval auto-enabled.
6. Learner names/scores land in any ledger, or a filled payload enters the repo tree.
7. record-class needs record-class-specific branching, or a future action needs core Python.
8. A core module gains a host token or non-stdlib dependency.
9. Tests use a real DB / real subprocess, or coverage drops below the many-tests culture.

## Rollout (ordered, independently shippable)

- **Tier 0 — PRIVATE workspace, interim, no code (today):** add a record-class
  `write-action-v1` template JSON + filled-payload example under
  `.chat-lms-state/write-actions/` + a runbook so SQL is no longer hand-authored ad hoc.
- **Tier 1 — PUBLIC repo, core engine + tests:** `write_actions.py` + `write_engine.py`
  + full hermetic suite (the trust core; bulk of effort). No CLI/route yet.
- **Tier 2 — PUBLIC repo, CLI + route + registry:** `write_action_handlers.py`, wire
  `commands.py` `write-action`, repo `routes/record-class.json` +
  `write-actions/record-class.json`, flip `agent_tools.py` `academy-db` placeholder to an
  active `write-action` `database_workflow` entry (+ `tool:write-action` memory obligation).
  Profile shortcut `기입.json` is private. No Codex-config change (hooks inert under Codex).
- **Tier 3 — PRIVATE workspace, register + approve:** scaffold → `validate_template` →
  promote active via real-terminal isatty+typed-id approval (+ `--evidence` = Tier 1/2 tests);
  single-use consumed. Daily replay then unattended.
- **Tier 4 — PRIVATE, backfill session 579:** replay with corrected attendance via `update_stub`.
- **Tier 5 — LATER, PUBLIC:** a second template (enroll/adjust-scores) proves cheapness;
  fold in the overhead-Tier-2 reductions (py version-check, hook fast-exit, bootstrap hash-gate).

## Open risks

1. `compile_plan` identifier assembly is the most security-sensitive path — allowlist must come
   ONLY from `table_whitelist`+`columns`, never payload keys; needs focused adversarial tests.
2. Trigger-awareness is author-encoded per step; a wrong op in a FUTURE template could re-introduce
   stub duplication — mitigated by `validate_template` + approval review, not structure alone.
3. `columns` allowlist couples templates to live schema; add a `write-action doctor` PRAGMA-drift check.
4. The four-op vocabulary can't express joins/conditionals — firmly hold "doesn't fit ⇒ not a
   write-action" to avoid a SQL escape hatch.
5. **`pre_tool_gate` does NOT currently block a raw sqlite-mutating one-liner against
   `data/chat_lms.db`** (not in `_PRIVATE_DATA_MARKERS`). The engine is the easier path, not the
   only one. Follow-up: add `data/chat_lms.db` + bare `.db` to the markers and tier sqlite-mutating
   one-liners as writes, so the gate truly funnels writes through the CLI.
6. WAL-checkpoint-then-copy assumes a single writer (safe for single-teacher desktop).
7. Demoting `--actor` is correct, but the shared `approvals.py` actor-string hole still exists; this
   design depends on (and re-tests) the isatty+typed-id gate rather than the actor string.
