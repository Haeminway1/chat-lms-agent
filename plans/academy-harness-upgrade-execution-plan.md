# Academy Harness Upgrade — Sliced Execution Plan

Status: **EXECUTION PLAN (approved scope, slice-by-slice).** Single source of truth for
sequencing the work. Companion design docs (the "what/why/how" detail each slice
implements against): `academy-write-workflow-engine-plan.md` (write engine) and
`runtime-diagnosis-and-isolation-findings.md` (diagnosis + isolation). This file owns the
"in what order, how verified, how committed."

## Operating protocol (roles + cadence)

- **Implementation = LazyCodex ulw-loop**, run in a Codex DEV session in the PUBLIC repo
  `C:\dev_projects\chat_lms_agent` (dev context — ulw-loop is appropriate HERE; it is the
  runtime/teacher sessions we isolate it FROM, per the isolation findings). ulw-loop does
  TDD red→green, runs gates, and commits the slice.
- **Review + direction = Claude Code (this agent).** I do NOT write feature code. Per
  slice I (1) produce a paste-ready ulw-loop brief, (2) after ulw-loop's commits land,
  independently REVIEW (re-run gates, read the diff, check the slice's success/failure
  criteria + the design invariants, adversarially probe), (3) either APPROVE → next slice,
  or return concrete corrections to ulw-loop. I am the independent QA agent; ulw-loop is
  the coding agent (satisfies the team rule).
  > Handoff reality: Claude Code cannot launch a Codex ulw-loop session. The loop is:
  > I emit the brief → you run `ulw: <brief>` in Codex (public repo) → commits land →
  > I review here → I emit the next brief. I drive the plan/review cadence; ulw-loop codes.

## Per-slice rules (every slice, no exceptions)

1. **Design-first** is already done (the two companion docs); a slice may not invent scope
   beyond them — scope creep → bounce back to planning.
2. **TDD**: write failing tests first (RED), then implement (GREEN). Many tests, edge cases,
   hermetic (injected seams, NO real DB / NO real subprocess), per the repo culture + the
   global rule.
3. **Gates before commit**: `uv run ruff check` && `uv run basedpyright` && `uv run pytest -q`
   (+ the linux-ignore run where the repo uses it). RED→GREEN evidence captured under
   `evidence/` per existing convention.
4. **One slice = one commit**, conventional-commit message, on the feature branch. **Working
   tree CLEAN before the next slice starts** (no dirty repo carried between slices).
5. **Public-safety**: no learner data / names / scores / machine paths in the repo; templates
   are identifiers-only; filled payloads + DB live in the private profile. `test_repo_privacy`
   + `test_host_independence` stay green.
6. **My review gate** must pass before the next brief is issued.

Branch: `feat/academy-harness-upgrade` (all slices). Pre-existing unrelated working-tree
changes (classcard_* edits + their new tests) are NOT part of this plan — leave them to the
user; do not sweep them into slice commits.

**HARD INVARIANT — ClassCard upload is a must-keep feature.** No slice, refactor, or isolation
step may remove or regress ClassCard upload (`classcard` CLI commands, `routes/classcard.json`,
the `tool:classcard` agent-tools entry, or the `classcard_*` modules). It uses its own bundled
Playwright (not omo/Codex browser plugins), so it keeps working under the isolated teacher
CODEX_HOME (chat-lms-agent@chatlms enabled). The pre-existing classcard working-tree edits are
the user's in-progress work — preserve them; never delete/revert. Every review verifies
classcard routes/tests/registry stay intact.

---

## Epic A — Write capability (kills the 2–4 min 기입; the headline win)

Implements `academy-write-workflow-engine-plan.md`. Generic `write-action` engine; record-class
is the first DATA template, zero record-class-specific Python.

### Slice A1 — `write_actions.py`: template + loader + compiler (PURE, no DB)
- **Build:** `WriteActionTemplate`/`WriteStep` dataclasses (four ops: resolve/insert/ensure/
  update_stub; NO `sql` field), `load_write_actions(repo_root, profile)` (repo then profile,
  profile-wins, tolerant skip — mirror `route_packs.py`), `compile_plan` (lowers steps to
  `(sql_text, bind_order, captures)`; identifiers ONLY from `table_whitelist`+`columns`;
  values ALWAYS `?`), `validate_template` (register-time structural check).
- **Tests:** loader (profile-wins, malformed skip, schema-version gate, BOM); param validation
  (required/type/enum/date/range); **whitelist enforcement** (off-list table/column/`@ref`/op
  → error; assert no param value appears in `sql_text`); `validate_template` rejects ill-formed;
  `$arr[].field` fan-out / `='literal'`.
- **Success:** compiler is pure (no DB import), no `sql` field anywhere, every value binds as
  `?`, gates green. **Failure:** any identifier/value interpolation path, or compiler touches a DB.
- **Commit:** `feat(write): add write-action template loader + plan compiler (write-action-v1)`

### Slice A2 — `write_engine.py`: the one executor (DB, injected seam)
- **Build:** `run_write_action(profile, template, params, *, db_path, connect=…, now=…)`:
  pin db_path under `profile.root/data` (else exit 4); **binary-safe backup** (WAL-checkpoint +
  `shutil.copyfile`, NOT `academy_db.create_backup`'s text copy); one explicit transaction;
  trigger-aware ops; ID/count-only audit via `journal`.
- **Tests (real trigger in DDL fixture, injected `connect`):** trigger UPDATE-not-INSERT +
  no-duplicate (session-579 regression); attendance-NULL repair; make-up no-stub insert;
  mid-txn error → ROLLBACK leaves DB byte-identical + names step_id; backup
  `PRAGMA integrity_check==ok` + target==write-target; `--db` outside profile/under repo →
  exit 4 no-connect; lookup miss → exit 2 no-write; isolation_level not None.
- **Success:** all the above pass; both new modules host-token-free + zero-dep. **Failure:**
  text-copy backup, blind-INSERT over stubs, backup≠write target, or `--db` escapes profile.
- **Commit:** `feat(write): add transactional write-action engine (backup+rollback+audit)`

### Slice A3 — CLI surface + exit-code contract
- **Build:** `write_action_handlers.py` (subcommands `plan`/`apply`/`list`/`explain`/`doctor`,
  mirror `academy_db_handlers.py`); wire `commands.py` `_dispatch` `"write-action"`; exit codes
  0/2/3/4/5 exactly.
- **Tests:** handler dispatch; `plan` dry-run = 0 writes + predicted counts; `apply` exit-code
  mapping; non-active template → NEEDS_APPROVAL(3).
- **Commit:** `feat(write): add write-action CLI (plan/apply/list/explain/doctor)`

### Slice A4 — record-class data template + route + registry
- **Build:** repo `write-actions/record-class.json` (reference template, public-safe);
  `routes/record-class.json` (route-pack-v2, `기입` + aliases, first/then = plan/apply,
  must_not = "no manual SQL / UPDATE stubs not blind-INSERT"); flip `agent_tools.py` `academy-db`
  placeholder → active `write-action` `database_workflow` entry (+ `tool:write-action` memory
  obligation); `docs/` + `docs/architecture.md` line.
- **Tests:** record-class compiles + all four ops exercised end-to-end on the fixture;
  `test_repo_privacy` passes on the new repo files; registry/agent-tools tests updated.
- **Success:** a 기입 = LLM fills payload → `plan` → `apply`, zero SQL by the model.
- **Commit:** `feat(write): ship record-class template + 기입 route + registry entry`

---

## Epic C — Auto-isolation distribution (the product requirement)

Make `bootstrap.ps1` stand up a clean, contamination-free teacher Codex environment
automatically, so any instructor (even with a global dev stack like omc) downloads + sets up
and gets an isolated chat-lms workspace. Mechanism per the isolation findings: a dedicated
`CODEX_HOME` + launcher; dev `~/.codex` untouched.

### Slice C1 — bootstrap creates the isolated teacher CODEX_HOME + launcher
- **Build:** extend `scripts/bootstrap.ps1` (User mode) to idempotently create a clean teacher
  `CODEX_HOME` (default e.g. `%USERPROFILE%\.codex-<profile>` or under the profile root), write
  a minimal `config.toml` (model; approval/sandbox posture; `[features] plugins+plugin_hooks`
  only — OMIT `child_agents_md`/`multi_agent`/`enable_fanout`; the workspace `[projects.*]`
  trust line; `[marketplaces.chatlms]` source = this repo's `codex-plugin`; enable ONLY
  `chat-lms-agent@chatlms`; NO omo / `[agents.*]` / `shell_environment_policy.set`), register
  the chatlms marketplace against that home, and generate a labeled launcher (`.cmd` setting
  `CODEX_HOME` + launching by AUMID `OpenAI.Codex_2p2nqsd0c76g0!App`). Public-safe; absolute
  paths confined to the generated private artifacts, never the repo.
- **Tests:** mirror `tests/test_bootstrap_v2.py` content checks — generated config OMITS
  `child_agents_md`/omo/`[agents.*]`, ENABLES only chat-lms, has the trust + marketplace lines;
  launcher sets CODEX_HOME + uses AUMID; idempotent re-run; the writer does NOT touch the dev
  `~/.codex`. (Hermetic: write to a temp home, assert file contents — no real Codex.)
- **Success:** one bootstrap run yields a clean home + launcher; dev home provably untouched.
  **Failure:** generated config inherits any dev plugin/feature, or the writer edits `~/.codex`.
- **Commit:** `feat(bootstrap): auto-provision isolated teacher CODEX_HOME + launcher`

### Slice C2 — distribution onboarding + runbook
- **Build:** README/AGENTS distribution section ("download → bootstrap → click the labeled
  launcher → one-time login + trust approval → use"); the two irreducible manual steps
  documented plainly; the "graduate" option (dedicated Windows account, CODEX_HOME at User
  scope). Update `docs/` contracts.
- **Tests:** `test_docs_contract` stays green; doc references resolve.
- **Commit:** `docs(bootstrap): distribution + isolated-runtime onboarding runbook`

---

## Epic B — Read fast-paths (so retrieval is also one step)

"오늘 EBSS 기록 보여줘 / 이 반 최근 점수" currently improvises like writes did.

### Slice B0 — read mini-design (Claude Code, before coding)
- I produce a short appended design: decide read mechanism (preferred: **read-action templates =
  SELECT-only plans reusing the A1 compiler's parameterized-SELECT path**, vs named queries
  against `chat_lms.db`), resolve the store-split (academy-db JSON store vs legacy `chat_lms.db`
  — reads must hit the real DB the viewer reads), define the read templates + routes. Output:
  success/failure criteria for B1/B2. **No code.**

### Slice B1 — read execution + B2 — read routes/shortcuts
- Implement per B0 with hermetic tests (read-only, injected seam); bind common reads to routes
  + a shortcut; reads never mutate. Commits: `feat(read): …` per slice.

---

## Epic D — Overhead + gate hardening (polish; latency-findings Tier 2)

### Slice D1 — per-call + session-start overhead
- Drop the redundant `py -3` version pre-check from the hot path (in the bootstrap TEMPLATE so
  it isn't overwritten); shell-level fast-exit for no-op Pre/PostToolUse in `chat-lms-hook.ps1`;
  hash-gate the SessionStart bootstrap sync (skip when public-repo unchanged; stop the
  self-rewrite double-run). Tests for the gate logic.
- **Commit:** `perf(hooks): fast-exit no-op hooks, drop version pre-check, hash-gate sync`

### Slice D2 — pre_tool_gate funnels DB writes through the CLI
- Add `data/chat_lms.db` + bare `.db` to `_PRIVATE_DATA_MARKERS`; tier sqlite-mutating
  one-liners as writes so raw-SQL bypass is gated and writes funnel through the write-action CLI.
  Tests for the new gate decisions.
- **Commit:** `feat(gate): funnel raw DB writes through the write-action CLI`

---

## Manual / private steps (NOT ulw-loop — user + Claude Code together)

- **M-clean:** delete the dev-orchestration litter in the private workspace
  `…\codex-workspace\.omo\ulw-loop\019ebaba-…\` (contains real student data). Do early.
- **M-home:** run the C1 bootstrap to stand up the real teacher CODEX_HOME; one-time
  `codex login` + chat-lms hook-trust approval; verify isolation (no Boulder/ultrawork/git_bash
  in a teacher session).
- **M-register:** after A4, register + approve the record-class write-action from a real
  PowerShell TTY (Desktop has no TTY) with `--evidence` = the A1–A4 test runs; single-use consume.
- **M-backfill:** after the engine works, repair 2026-06-15 session 579 `attendance=NULL` via
  the deterministic writer; verify with read queries.

---

## Recommended order

A1 → A2 → A3 → A4 (kill 기입 pain) → C1 → C2 (isolated distribution) → B0 → B1 → B2 (reads) →
D1 → D2 (polish). Slices are mostly independent; C can run in parallel with A in a separate
ulw-loop if desired. Manual M-clean can happen anytime; M-home/M-register after C1/A4.

## Definition of done (whole effort)

기입 drops from 2–4 min to single-digit seconds (1 LLM turn + plan + apply); reads are one
routed step; a fresh instructor gets an isolated, contamination-free teacher Codex env from
one bootstrap + two security clicks; dev sessions keep Sisyphus untouched; full suite green;
repo clean and public-safe throughout.
