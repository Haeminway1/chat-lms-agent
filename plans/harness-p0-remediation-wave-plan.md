# Harness P0 Remediation Wave Plan

## Purpose

This is the implementation wave plan for the nine P0 items from the 2026-06-10
golden-standard gap analysis. It precedes and unblocks the V5 plan
(`plans/harness-v5-extensibility-and-independence-plan.md`): V5 Track B Wave B3
explicitly depends on Waves 1-3 of this plan.

The gap analysis verdict in one line: the harness's governance ideas
(closeout gate, approval ledger, privacy boundary) are correct and in several
cases unique, but their enforcement contracts are weaker than they look —
one enforcement point speaks a dialect the host may not honor, one is a dead
seam, pre-execution gating is absent, and the trust base (tests, CI, ledgers)
has bypass routes. P0 fixes exactly that, without adding any new product
surface.

## Plain-Language Model

The workshop already has good rules. P0 makes the rules physical:

- The "cannot close the workshop with unrecorded knowledge" sign becomes a
  door that actually locks (native decision contract), and the door stops
  slamming forever when only the owner can unlock it (loop guard).
- A notice nailed to a door nobody opens (PostCompact stdout) moves to a door
  people actually use (SessionStart recovery).
- A doorman is hired (PreToolUse) so dangerous actions are stopped before
  they happen, not discovered after.
- The intercom stops repeating the full rulebook on every sentence (context
  diet).
- Approval stamps require a human hand at a real keyboard (isatty gate).
- The workshop inventory is merged into one list (store composition), the
  safety inspectors get their own clean room (test hermeticity), and an
  inspector visits on every change (CI).

## Verified Current State (line-level evidence)

All claims below were verified directly in the working tree on 2026-06-10.

- `src/chat_lms_agent/commands.py:175` routes both `stop` and `post-compact`
  to `write_closeout`. Host documentation surveyed in the gap analysis
  (oh-my-codex `docs/codex-native-hooks.md`, lazycodex
  `components/rules/src/hook-output.ts`) indicates compact events do not
  accept stdout, making the post-compact branch a dead enforcement seam.
- `src/chat_lms_agent/session_closeout.py:19-32` emits
  `{"status": "BLOCKED", ...}` with exit 5 and no `decision`/`reason`
  fields, so the Stop gate does not speak the native continuation contract.
- `src/chat_lms_agent/hook_payloads.py` parses only
  `event_name/changed_files/session_id/prompt`. `stop_hook_active`,
  `source`, `trigger`, `tool_name`, `tool_input` are discarded;
  `_read_stdin` (line 67) has no size cap.
- `hooks/hooks.json` registers five events; there is no PreToolUse entry, so
  no pre-execution gate exists anywhere.
- Context payload is rebuilt and emitted on SessionStart, every
  UserPromptSubmit, and every PostToolUse (`commands.py` hook dispatch into
  `context.py build_codex_context`), with no dedup, no per-section budget,
  and volatile `record_count` fields that change the blob every event.
- `tests/` has no `conftest.py`; hook tests inherit ambient env
  (`os.environ.copy()`), so a developer machine with
  `CHAT_LMS_AGENT_PROFILE_ROOT` set can leak test writes into a real
  profile. Several hook tests accept `returncode in {0, 5}`.
- `approvals.py` rejects only the self-reported agent actor string;
  `approval approve --actor teacher` typed by the agent passes.
- `agent_tool_reuse.py` and `context.py` never read
  `agent_tool_lifecycle._load_records`, so lifecycle-promoted tools are
  invisible to reuse checks and hydration.
- `git ls-files` shows no `.github/`: no CI.

## External Patterns Borrowed (structural reference only, no code copying)

| Pattern | Source | Used in |
| --- | --- | --- |
| Stop-hook continuation contract `{"decision":"block","reason":<directive>}` with re-engagement directive text | lazycodex `components/start-work-continuation` | Wave 2 |
| `stop_hook_active` no-op guard + context-pressure suppression | lazycodex `start-work-continuation/src/codex-hook.ts` | Wave 2 |
| Same-blocker escalation to a named human decision after N repeats | oh-my-codex `ulw-loop` checkpoint escalation | Wave 2 |
| Compact-recovery claim flag re-injected once at the next safe event | lazycodex `post-compact-claim.ts`, `markSessionCompacted` | Wave 2 |
| PreToolUse Bash matcher emitting `permissionDecision: "deny"` | lazycodex `hooks/hooks.json`, oh-my-codex `codex-native-pre-post.ts` | Wave 3 |
| Dangerous-pattern command screening with normalization | hermes-agent `tools/approval.py` DANGEROUS_PATTERNS | Wave 3 |
| Approval-tier decision algebra: per-action tier (`read\|write\|exec`, computable from arguments) x mode x per-action policy (`allow\|deny\|prompt`) x critical-pattern override that beats `allow` — a pure decision table | oh-my-pi `tools/approval.ts`, `docs/approval-mode.md` | Wave 3 |
| Runtime-owned state directory unwritable by agent file tools | gajae-code `.gjc/**` mutation guard | Wave 3 |
| Hook stdin byte cap | oh-my-codex `hook-payload-guard.ts` | Wave 1 |
| Token/byte regression ledger: constants imported from production source by tests | gajae-code `orchestration-token-benchmark` | Wave 4 |
| Per-rule char caps + truncation markers; injection dedup per session | lazycodex `rules/constants.ts`, `persistent-cache.ts` | Wave 4 |
| Zero-token bilingual keyword recall with strict char budgets | roach-pi `extensions/workspace-memory/recall.ts` | Wave 4 |
| Interactive-presence approval (root-only ask; human channel) | roach-pi root-only `ask_user_question`, hermes human approval channels | Wave 0 |
| Hermetic test home redirection via autouse fixture | hermes-agent `tests/conftest.py _isolate_hermes_home` | Wave 0 |

## Must NOT Have

- No new product surfaces: P0 adds no commands beyond the PreToolUse hook
  verb and flags required by the fixes.
- No LLM calls, no network, no new runtime dependencies.
- No writes to host-owned config (Codex `config.toml` keys stay untouched).
- No weakening of any existing gate to make a test pass; `{0,5}` tolerances
  are replaced by exact per-event expectations, never widened.
- The Stop gate must never block on conditions a teacher cannot resolve from
  the directive text alone (every BLOCKED reason carries its remediation
  commands).
- PreToolUse deny rules must be deterministic stdlib checks — no heuristic
  scoring, no model calls.

## Waves And Tasks

Run waves in order; tasks inside a wave are parallel-safe unless noted.
Every task is red -> green: the red test is written and observed failing
before implementation, transcripts captured per the local evidence
convention.

### Wave 0 — Trust foundations (no dependencies; start immediately)

- T0.1 Test hermeticity (P0-8).
  - Red: `tests/test_conftest_hermeticity.py::test_profile_env_is_isolated`
    — sets `CHAT_LMS_AGENT_PROFILE_ROOT` to a sentinel path at session
    scope, asserts no test-visible command writes there;
    `::test_secret_env_blanked` asserts `*TOKEN*`/`*SECRET*` env vars are
    absent inside test subprocess env.
  - Green: new `tests/conftest.py` autouse fixture: delete
    `CHAT_LMS_AGENT_PROFILE_ROOT`, blank secret-pattern env vars, redirect
    profile root to a per-test tmp dir; helper for subprocess env
    construction shared by CLI tests.
  - Files: `tests/conftest.py` (new), touched tests that build env dicts.
- T0.2 CI (P0-9).
  - Red: none (infrastructure); acceptance is the workflow run itself.
  - Green: `.github/workflows/ci.yml` — `windows-latest` primary lane
    (`uv sync`, `ruff check`, `basedpyright`, full `uv run pytest` including
    bootstrap and hook subprocess tests), `ubuntu-latest` secondary lane
    (pure-Python suite). Trigger: push + pull_request.
  - Note: Windows is the primary lane because the safety surface
    (bootstrap.ps1, generated hooks) is PowerShell.
- T0.3 Tool store composition (P0-7; identical to V5 Task A0.1 — implement
  once, credit both plans).
  - Red: `tests/test_agent_tools_reuse_check.py::test_reuse_check_sees_lifecycle_promoted_tool`
    — scaffold+promote a lifecycle tool in a tmp profile, assert
    `reuse-check` matches an intent against it (currently fails).
  - Green: one composed read helper (static registry + legacy `tools.json`
    + `agent_tool_lifecycle._load_records`, each entry tagged `source`,
    redacted) consumed by `agent_tool_reuse.reuse_check_payload`,
    `agent_tools` listing, and `context.py` hydration.
  - Files: `agent_tools.py`, `agent_tool_reuse.py`, `context.py`.
- T0.4 Approval human presence (P0-6).
  - Red: `tests/test_trace_audit_approval.py::test_approve_rejected_without_tty`
    — `approval approve` with non-tty stdin returns exit 5 and
    `error_code: APPROVAL_REQUIRES_INTERACTIVE`;
    `::test_approve_requires_typed_id_confirmation` — interactive path
    requires re-typing the approval id.
  - Green: isatty gate + typed-id confirmation in the approve path;
    `--actor` demoted to audit metadata only. Test seam: an explicit
    `--assume-tty-for-tests` flag is rejected outside pytest tmp profiles,
    or stdin monkeypatch at handler level (decide in red phase; the gate
    itself must not gain a production bypass flag).
  - Files: `approval_handlers.py`, `approvals.py`, `cli_io.py`.

### Wave 1 — Hook payload plumbing (prerequisite for Waves 2-3)

- T1.1 Stdin cap.
  - Red: `tests/test_hook_payloads.py::test_oversized_stdin_rejected` —
    >1 MiB stdin returns `INVALID_HOOK_PAYLOAD` with
    `reason: "payload too large"`, never raises.
  - Green: bounded read in `_read_stdin` (`hook_payloads.py:67`).
- T1.2 Payload field extension.
  - Red: `tests/test_hook_payloads.py::test_lifecycle_fields_parsed` —
    fixture payloads carrying `stop_hook_active`, `source`, `trigger`,
    `tool_name`, `tool_input` round-trip into `HookPayload`; unknown/missing
    fields default safely (`stop_hook_active=False`, others `None`).
  - Green: extend the frozen dataclass and parser; keep tolerant-key
    behavior consistent with existing `_prompt_text` style.
  - Files: `hook_payloads.py`, fixtures under `tests/`.
- T1.3 Session-scoped counter store (minimal slice of the session model;
  the full model stays in gap-roadmap item 11).
  - Red: `tests/test_hooks.py::test_block_counter_scoped_by_session` — two
    different `session_id` values keep independent counters under
    `<profile-root>/.chat-lms-state/sessions/<session-id>/`.
  - Green: small helper in `state.py` (path sanitization reused from
    profile-root rules); atomic write like existing stores.

### Wave 2 — Closeout contract correction (after Wave 1)

- T2.1 Native Stop continuation contract (P0-1).
  - Red: `tests/test_session_closeout_v2.py::test_blocked_payload_carries_decision_and_reason`
    — BLOCKED closeout JSON contains `decision: "block"` and a non-empty
    Korean `reason`; `::test_reason_embeds_remediation_commands` — reason
    text includes the exact `memory draft`/`memory apply-draft` command for
    each missing key, the pending `approval_id` with a "teacher approval
    required" note, and the import-plan apply command.
  - Green: extend both BLOCKED branches in
    `session_closeout.py write_closeout` (lines 19-32); keep `status` and
    exit codes unchanged for CLI consumers; reason rendered from existing
    payload data only.
  - Files: `session_closeout.py`; message strings prepared for the future
    ko/en catalog (gap-roadmap item 18) but hardcoded Korean is acceptable
    in this wave.
- T2.2 Stop-loop guard (P0-2; depends on T1.2, T1.3).
  - Red: `tests/test_hooks.py::test_stop_hook_active_is_noop` —
    `stop_hook_active: true` returns PASS exit 0 without closeout
    evaluation; `::test_third_identical_block_escalates` — same blocker
    signature three times yields PASS-with-warning naming the blocked human
    action in Korean and stamps an `escalated` marker in the session dir.
  - Green: guard in the hook stop path before `write_closeout`; blocker
    signature = sorted missing keys + pending approval ids + plan ids;
    counter in the session store from T1.3.
  - Files: `commands.py` hook dispatch, `session_closeout.py`,
    `state.py` helper.
- T2.3 PostCompact correction (P0-3; depends on T1.2).
  - Red: `tests/test_hooks.py::test_post_compact_emits_nothing` —
    `hook post-compact` writes a recovery marker, emits no stdout, exits 0;
    `tests/test_context_hydration_v2.py::test_session_start_compact_recovery_injected_once`
    — with a pending marker, session-start context contains a
    `compact_recovery` section (memory obligations, pending approval ids,
    unapplied plans, goal summary) exactly once across two consecutive
    session-start events (claim semantics); `::test_user_prompt_submit_is_fallback_claim`.
  - Red (same task): replace `returncode in {0, 5}` in
    `tests/test_hooks.py` with per-event exact expectations (PostCompact
    pinned to `{0}`).
  - Green: remove `"post-compact"` from the closeout set at
    `commands.py:175`; marker file `compact-recovery.json` with
    claimed/recovering flags; recovery section renderer in `context.py`.
  - Files: `commands.py`, `context.py`, `hook_payloads.py` consumers,
    `hooks/hooks.json` (drop `--verify-memory` from PostCompact),
    `scripts/bootstrap.ps1` generated config equivalents.

### Wave 3 — PreToolUse safety gate (P0-4; after Wave 1)

- T3.1 Registration.
  - Red: `tests/test_hooks.py::test_pre_tool_use_registered_and_executes`
    — repo `hooks/hooks.json` and the bootstrap-generated config both carry
    a PreToolUse entry; fixture payload executes without traceback.
  - Green: `hook pre-tool-use` verb; hooks.json + bootstrap template update;
    `harness_context.HOOK_EVENTS` updated (doctor lifecycle check follows
    automatically).
- T3.2 Deny rules structured as an approval-tier decision table
  (deterministic, stdlib-only; oh-my-pi `tools/approval.ts` as the
  structural reference; one red/green per rule class).
  - Shape: every gated action is classified to a tier (`read | write |
    exec`) computed from `tool_name` + `tool_input`; a teacher policy table
    (per action class: `allow | deny | prompt`) overlays the harness mode;
    critical patterns carry `override(reason)` that forces
    `NEEDS_APPROVAL` even where policy says allow, with the reason embedded
    in the decision payload. Defaults are inverted from the reference:
    unknown action classes resolve to `prompt`, never `allow`.
  - Red (table-level): `tests/test_pre_tool_use_gate.py::test_decision_table_truth_table`
    — exhaustive tier x policy x override matrix asserted as pure data
    before any individual rule lands.
  - Rule A — destructive command × private data path without approval:
    `tests/test_pre_tool_use_gate.py::test_destructive_db_command_denied`
    — bash `tool_input` matching destructive verbs (`Remove-Item -Recurse`,
    `del /s`, `format`, `reg delete`, `git push --force`, `rm -rf`) against
    profile DB/state paths is denied unless a consumable approval id
    exists; with an approved ledger entry it passes and the approval is
    referenced (not consumed — consumption stays with the operation
    itself).
  - Rule B — runtime-owned ledgers:
    `::test_state_dir_mutation_denied` — edit/write/bash mutations
    targeting `.chat-lms-state/**` are denied with
    `error_code: RUNTIME_OWNED_STATE` and the sanctioned CLI named in the
    message (gajae trait: ledgers are runtime-owned).
  - Rule C — boundary export:
    `::test_public_repo_write_with_private_reference_denied` — writes
    landing under the public repo whose content references private profile
    paths are denied (boundary direction: private must not leak into
    public).
  - Green: pure functions in a new `pre_tool_gate.py` returning
    allow/deny + reason; hook path emits the host dialect
    `{"permissionDecision": "deny", "reason": ...}` (dialect kept in one
    place for V5 B2/B3 adapter extraction).
- T3.3 Audit trail.
  - Red: `::test_denials_are_journaled` — every deny writes a trace record
    via `journal.py` with rule id and redacted command summary.
  - Green: journal call in the deny path (redaction through existing
    `redact_runtime_text`).

### Wave 4 — Context injection diet (P0-5; independent of Waves 2-3, after
Wave 0)

- T4.1 Budget regression gate first (gajae ledger trick).
  - Red: new `tests/test_context_budget.py` pinning current truth before
    any optimization: empty-profile payload <= 10,000 bytes; 50-memory
    fixture payload <= 22,000 bytes; per-section ceilings (memory,
    oss_reference_registry, side_panel, tool registry) asserted against
    constants imported from `context.py` (`CONTEXT_SECTION_BYTE_CEILINGS`,
    `CONTEXT_EVENT_BYTE_CEILING`); determinism: same inputs twice ->
    byte-identical payload (sha256).
  - Green: declare the constants in `context.py`; make the payload
    deterministic by removing volatile fields (next task) so the sha256
    assertion can pass.
- T4.2 Remove volatility.
  - Red: `::test_payload_stable_across_journal_growth` — appending a trace
    record does not change the hydration payload.
  - Green: drop live `record_count` from injected blobs; counts become
    on-demand (`trace list`/`audit list` already expose them).
- T4.3 Event tiering.
  - Red: `::test_user_prompt_submit_emits_route_and_delta_only`,
    `::test_post_tool_use_emits_only_on_obligation` — UserPromptSubmit
    payload contains prompt-route + deltas (new memory keys, new pending
    approvals) and no full static sections; PostToolUse emits additional
    context only when an obligation fires.
  - Green: tier table in `context.py`; SessionStart remains the full
    payload; session-scoped dedup marker (T1.3 store) suppresses repeat
    static sections.
- T4.4 Memory selection and write caps.
  - Red: `tests/test_harness_memory.py::test_levels_enforced_in_hydration`
    — entries whose level sets `hydrated_by_default=false` stay out of
    SessionStart payload; `::test_prompt_scoped_topk_recall` — on
    UserPromptSubmit, top-K (K=5) entries selected by bilingual keyword
    scoring (Korean token regex + English tokens, stopword lists) within an
    8,000-byte budget; `::test_upsert_write_cap` — oversized `memory
    upsert` text is rejected with a "X/Y bytes" message.
  - Green: add `level` to `MemoryPayload` (`state.py`) with migration
    default; scorer module (stdlib only, roach-pi recall as the structural
    reference); caps in `memory_handlers.py`.
- T4.5 Reduction ledger.
  - Red: `::test_applied_reductions_pinned` — an `APPLIED_REDUCTIONS`
    structure in `context.py` records each diet step and the test asserts
    the measured empty-profile/50-memory payloads against the post-diet
    ceilings (tightened from T4.1 values).
  - Green: tighten ceilings; silent regressions now fail tests.

## Development Method, Test Plan, Success And Failure Criteria

Development method:

- Wave order 0 -> 1 -> 2 -> 3 -> 4 (3 and 4 may swap or overlap; both
  depend only on earlier waves). Red transcript captured before green per
  task, evidence stored per local convention, goal-ledger entries with
  independent QA verification (`qa_verifier_status`) per goal — the
  implementer never verifies their own goal.
- Every wave ends with the full local gate: `uv run pytest`, `ruff check`,
  `basedpyright`, plus from Wave 0 onward the CI run on a pushed branch.

Test plan:

- New test modules: `test_conftest_hermeticity.py`, `test_pre_tool_use_gate.py`,
  `test_context_budget.py`; extensions to `test_hook_payloads.py`,
  `test_hooks.py`, `test_session_closeout_v2.py`,
  `test_context_hydration_v2.py`, `test_harness_memory.py`,
  `test_agent_tools_reuse_check.py`, `test_trace_audit_approval.py`.
- All hook assertions move from `{0,5}` tolerance to per-event exact
  expectations.
- Privacy suite (`test_repo_privacy.py`) and docs contract suite must stay
  green untouched at every wave boundary.

Success criteria (all must hold):

- Stop BLOCKED output carries `decision: "block"` plus a Korean reason whose
  remediation commands are copy-paste runnable; `stop_hook_active` short-
  circuits; the third identical block escalates instead of looping.
- `hook post-compact` emits nothing and exits 0; recovery context is
  injected exactly once at the next session-start (or prompt-submit
  fallback).
- PreToolUse denies all three rule classes with journaled, redacted trace
  records; approved destructive operations pass.
- `approval approve` is impossible without an interactive terminal and a
  typed id confirmation.
- Reuse-check matches lifecycle-promoted tools; hydration lists them with
  source tags.
- Context payload is deterministic (sha256-stable), tiered by event, and
  within pinned ceilings; memory hydration honors levels and top-K recall.
- CI green on windows-latest and ubuntu-latest lanes; full suite green in a
  hermetic environment with `CHAT_LMS_AGENT_PROFILE_ROOT` poisoned.

Failure criteria (any one fails the wave):

- Any `{0,5}`-style tolerance remains or is widened anywhere in hook tests.
- The Stop gate can block on a condition whose remediation is not stated in
  its own reason text.
- PreToolUse gains a heuristic/scored rule or any rule requiring network or
  model calls.
- An approval can be created or approved by a non-interactive caller.
- Context ceilings are raised to make a test pass without a recorded
  `APPLIED_REDUCTIONS` justification.
- Any existing test is deleted or weakened; privacy suite regresses.

## Rollout And Rollback

- Each wave lands as one reviewed change set; hooks.json and bootstrap
  template changes ship in the same change as their tests (the private
  workspace self-sync then propagates them on next session start).
- Rollback unit is the wave: every wave leaves the previous waves' tests
  green, so reverting the latest wave restores a known-good gate state.
- Wave 2 carries the only behavior-visible risk (Stop output shape):
  mitigated by keeping `status`/exit codes unchanged so existing CLI
  consumers and tests that read `status` are unaffected.

## Roadmap Mapping

- Wave 0: gap-roadmap P0 items 6, 7, 8, 9 (item 7 == V5 Task A0.1).
- Wave 1: enabling slice for items 1-4; session store is the minimal slice
  of item 11.
- Wave 2: items 1, 2, 3.
- Wave 3: item 4 (and pre-stages the V5 B2/B3 host-dialect extraction).
- Wave 4: item 5 (and pre-stages item 23's telemetry fields).
- After this plan: V5 Waves A0/B1 may start immediately (A0.1 already done
  here); V5 B3 unblocks once Waves 1-3 land.
