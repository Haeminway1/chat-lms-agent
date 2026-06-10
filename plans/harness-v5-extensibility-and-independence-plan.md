# Harness V5 Extensibility And Independence Plan

## Purpose

V5 has two tracks driven by the 2026-06-10 golden-standard gap analysis
(lazycodex, oh-my-codex, gajae-code, roach-pi, hermes-agent) and by two product
constraints stated by the owner:

- Track A — Side-panel building blocks and daily prompt routes must become
  runtime-extensible through a draft -> preview -> promote pipeline, without
  weakening the no-from-scratch rule or the privacy boundary.
- Track B — The harness must stay model-agnostic and host-detachable: a
  three-tier model alias catalog (role -> family -> concrete model) and a real
  host adapter seam, while Codex Desktop remains the only executing host this
  cycle. The end state is a standalone desktop app / web SaaS that can swap
  models and hosts without rewriting the core.

The target architecture is unchanged from V4:

```text
Codex Desktop today
  -> Chat LMS reusable harness core
    -> private profile state, academy DB, memory, tools, audit, approvals, side-panel contracts
Future standalone desktop or Web SaaS later
  -> same reusable harness core through a different host adapter
```

V5 must not turn Chat LMS Agent into a replacement model runtime. It prepares
the seams so the runtime can be replaced later.

## Plain-Language Model

Continuing the teacher operations workshop metaphor:

- Building blocks are labeled furniture in the showroom. New furniture is
  built in the back room (draft quarantine), inspected (preview, tests,
  teacher approval), and only then moved to the showroom (catalog). Nothing
  goes from workbench to showroom in one step.
- The model catalog is a staffing chart. "Main model" is a role on the chart,
  "opus" is a job family, "claude-opus-4-8" is the specific hire. The chart
  lets the school re-staff any role without rebuilding the office.
- The host adapter is the translator at the door. The office speaks one
  internal language (harness-event-v1). Each landlord — Codex Desktop today,
  standalone desktop or web SaaS later — gets a translator, not a remodel.

## Current Baseline (verified findings)

Track A baseline:

- `side_panel.py` returns `PROPOSAL_REQUIRED` for unknown views, but there is
  no runtime path from proposal to promoted block. The 14-block catalog is
  static repo data.
- `agent_tool_lifecycle.py` already implements draft -> registered -> active
  -> deprecated with required contracts. This machinery exists for tools only,
  not for side-panel blocks.
- Prompt routes are code, not data: one hardcoded route in `prompt_routes.py`.
  Daily-use mappings cannot grow without a code change.
- Known defects to fix first (gap analysis 3.5): the three tool stores are not
  composed (reuse-check cannot see lifecycle-promoted tools), and
  `set_lifecycle_state` accepts arbitrary transitions without evidence.

Track B baseline:

- Model layer: zero model references in `src/chat_lms_agent`. The harness is
  model-blind by delegation (the host picks the model). Nothing blocks
  detachment, but nothing is prepared for it either: no catalog, no aliases,
  no role names.
- Host seam: `harness_events.py` defines the host-neutral envelope
  (`harness-event-v1`) and already names `standalone_desktop` and `web_saas`
  as future hosts. However the envelope is not the real ingress: the hook
  path (`commands.py` -> `hook_payloads.py`) parses the Codex dialect
  directly and never calls `normalize_event_file`.
- Host identity is hardcoded at multiple sites instead of being adapter data:
  - `approvals.py` `AGENT_ACTOR = "codex_desktop_agent"`
  - `context.py` `build_codex_context` and the literal runtime label
  - `context.py` and `side_panel_wordbook.py` `codex-workspace` directory name
  - `command_parser.py` `--for-codex` flag
  - `doctor.py` plugin/hooks checks treat host files as universal checks
  - `harness_events.py` default host string literals

## External Reference Decisions

Observed date: 2026-06-10. Structural references only; no source copying.

| Reference | Decision | What To Adopt | What Not To Copy |
| --- | --- | --- | --- |
| lazycodex `plugins/omo/model-catalog.json` | Structural reference | Versioned role catalog (`version`, `current`, `roles`, `managedProfiles`); migration safety: rewrite a value only when it matches a known managed profile, never a user-edited value. | npm auto-update daemon; writing host config files. |
| oh-my-codex `src/config/models.ts` | Structural reference | Three-step resolution order (specific key > default key > env override > built-in default); performance-tier aliases (frontier/standard/spark) as the family tier. | Reading or writing the host `config.toml`; env-first plumbing. |
| hermes-agent `hermes_cli/config.py` auxiliary block | Structural reference | Role-per-side-task naming (`auxiliary.<task>` -> provider:model) and fallback-chain vocabulary, reserved for future aux roles (summarizer, judge). | 28-provider plugin runtime, auxiliary LLM smart approval, gateway machinery. |
| gajae-code `packages/ai` model-manager | Reference only | Multi-source model metadata merge (static/cached/dynamic/remote) as the SaaS-phase shape. | Any of it now; no provider SDKs in this repo. |
| gajae-code draft-to-promoted artifact flow | Direct trait (already in `docs/golden-standards.md`) | Generated artifacts are drafts until tests, review, and evidence promote them — now applied to side-panel blocks. | Unreviewed generated UI. |
| hermes-agent skills hub + curator | Structural reference | Quarantine-before-install; usage-tracked lifecycle (promote what is used, archive what is not, never auto-delete). | Autonomous background self-improvement forks; hub network installs. |
| roach-pi workspace-memory usage scoring | Structural reference | Zero-token usage counters feeding promotion suggestions. | Embedding or remote recall services. |
| oh-my-pi `packages/catalog/src/identity/` (classify, equivalence, selection) | Structural reference | Canonical model identity: id classification (family/kind/version), concrete-rows-grouped-under-canonical-id with override > bundled > narrow-heuristic > fallback, deterministic variant comparator, "sessions always record the concrete model, never the alias", "ambiguous families never merge without explicit override". | The 40-provider runtime, wire-compat shaping, credential round-robin. |
| oh-my-pi `docs/models.md` context promotion | Structural reference | `context_promotion_target` as a catalog field: an overflow-recovery ladder orthogonal to roles/families; promotion is temporary and never rewrites role defaults. | Automatic model switching — ours is advisory-only this cycle. |
| oh-my-pi `docs/rulebook-matching-pipeline.md` | Structural reference | Single rule shape from many formats, name-keyed first-wins precedence, three buckets (always-inject / description-listed with lazy body / trigger-conditioned), tolerant per-file failure (one bad file never aborts discovery). | TTSR stream interception (requires owning the stream). |
| oh-my-pi `docs/secrets.md` two-mode contract | Structural reference (Track C) | Privacy data-file contract: reversible deterministic placeholders restored only on owner-facing display vs one-way replacement that never round-trips; plain/regex entries; project-over-global override. | Env-harvest defaults without owner review. |
| oh-my-pi `tools/report-tool-issue.ts` + `docs/install-id.md` | Structural reference (Track C) | Consent-gated local QA ledger: schema-level "never PII" field contract, one-time persisted consent state, local append-only buffer, race-safe exclusive-create install id. | Any remote submission endpoint. |
| oh-my-pi `tools/checkpoint.ts` yield-guard | Structural reference | Report-or-continue terminal contract: an open work unit cannot be closed without a closing report, enforced by the runtime rather than convention. | Live message-tree rewinding (host owns the transcript). |

## Must NOT Have (guardrails)

- No LLM calls, provider SDKs, embeddings, or network dependencies in this
  repo. Runtime dependencies stay at zero.
- No second agent runtime and no model switching inside the host. This cycle,
  the catalog is data plus resolution logic; Codex Desktop still owns
  execution.
- No agent-writable production catalogs. Block drafts live only in private
  profile quarantine; public-repo blocks change only through developer
  commits.
- No auto-promotion anywhere. Every block/route promotion requires a teacher
  approval through the existing approval ledger plus a memory obligation.
- No writes to host-owned config (for example the Codex `config.toml`
  approval/sandbox keys). Read-only posture checks at most, per the gap
  analysis anti-pattern list.
- Usage telemetry counts surface ids and timestamps only — never learner
  data, never prompt text.
- Default inversion rule for every oh-my-pi absorption: omp ships
  developer-trust defaults (yolo approval, headless-yolo subagents,
  telemetry prompts). Every borrowed mechanism lands here with the opposite
  default — always-ask, deny-unknown, consent-before-write — and a test
  pins the default.

## Track A — Block And Route Extension Pipeline

### A0. Prerequisites (from gap-analysis roadmap items 7 and 25)

- A0.1 Tool store composition: `agent_tool_reuse.reuse_check_payload`,
  `agent_tools` listing, and context hydration read one composed view of
  static registry + legacy `tools.json` + lifecycle records, each entry tagged
  with its source and passed through redaction.
  - Red: reuse-check test where a lifecycle-promoted tool must match an intent
    and currently does not.
  - Green: composed helper shared by all three read paths.
- A0.2 Evidence-gated lifecycle transitions: `set_lifecycle_state` validates
  the current state against an allowed-transition table and requires
  `--evidence` for promote; arbitrary jumps and deprecated revival fail with
  typed error codes.
  - Red: draft -> active jump currently succeeds; test asserts it must fail.
  - Green: transition table + evidence requirement.

### A1. Block lifecycle store and CLI

New module `side_panel_blocks.py` mirroring `agent_tool_lifecycle.py`:

- Per-profile store `block-lifecycle.json` with states draft -> registered ->
  active -> deprecated and the same transition validation as A0.2.
- Five block contracts required at scaffold time:
  - `render_contract`: JSON schema for the block payload (sections, fields).
  - `privacy_level`: one of the existing side-panel privacy levels.
  - `action_safety`: `requires_approval` and `dry_run_default` defaults for
    any action the block can host.
  - `test_contract`: the command that validates a sample payload.
  - `reuse_review`: checked-existing list against the 14 catalog blocks plus
    a custom-build justification (reuses the agent-tools shape).
- CLI verbs under `side-panel block`: `scaffold`, `register`, `preview`,
  `promote`, `deprecate`, `explain`, `list`.
- Closing-report contract (oh-my-pi yield-guard trait): a block record in
  draft/registered state is an open work unit. `deprecate` and any terminal
  transition require a short closing report (what was tried, verdict, where
  evidence lives) persisted on the record; session closeout surfaces open
  blocks as an advisory line so unfinished block work is never silently
  abandoned. Advisory this cycle; a `--strict-blocks` closeout flag may
  upgrade it later.
- Red/green per verb, matching the agent-tools test style
  (`tests/test_agent_tools_lifecycle_cli.py` as the template).

### A2. Quarantine draft area and no-from-scratch adjustment

- Drafts (schema, sample payload, optional draft HTML/CSS) live only under
  `<profile-root>/.chat-lms-state/side-panel-drafts/<block-id>/`. The
  production catalog loader never reads this directory.
- `side-panel block preview` validates the sample payload against the draft
  schema, runs the side-panel payload validator (privacy levels included), and
  emits a preview descriptor for the user-owned viewer. Preview never writes
  outside the quarantine.
- `tests/test_side_panel_no_from_scratch.py` keeps banning agent-generated
  HTML in the public repo and in promoted surfaces; it gains a clause that
  quarantine content is allowed only under the drafts directory and only while
  the block record is in draft/registered state.
- Promote requires: test_contract execution evidence, a `panel:<block-id>`
  memory obligation, and a consumable teacher approval (existing ledger).
  Promotion copies the validated schema into the per-profile active set; HTML
  remains user-owned (the teacher or developer places the final HTML, exactly
  as today for the 14 catalog blocks).
- Red: a draft block must not render through the production path; an
  unapproved promote must fail with `NEEDS_APPROVAL`.

### A3. Usage telemetry and promotion nudges

- Count view/block/route invocations in per-profile state: surface id,
  count, last-used timestamp. No learner data, no prompt text.
- Session closeout summary gains a `promotion_candidates` section listing
  draft blocks or repeated manual compositions whose usage crossed a
  threshold. This is a suggestion only; it never blocks closeout and never
  auto-promotes (hermes curator trait: suggest, archive proposal, never
  delete).
- Red: closeout summary without the section when telemetry is empty; with the
  section when a draft crosses the threshold.

### A4. Data-driven route packs (gap-analysis roadmap item 24)

- Routes move from code to data: `routes/` JSON in the public repo for
  defaults (the existing wordbook route becomes `routes/wordbook.json`), plus
  optional per-profile additions under profile state.
- Schema-validated at load (same strictness as side-panel payloads), passed
  through redaction, rejected with typed errors on conflict with repo
  defaults.
- Bucket model adopted from oh-my-pi `docs/rulebook-matching-pipeline.md`:
  every route/rule entry normalizes into one shape and lands in one of three
  buckets — always-inject (full card in hydration), listed-lazy (id +
  trigger summary in hydration, body served on demand by a CLI verb), or
  trigger-conditioned (injected only when the prompt matches). Precedence is
  name-keyed first-wins: profile pack > repo pack.
- Tolerant failure semantics (same source): one malformed pack file logs a
  typed warning and is skipped; it never aborts discovery or poisons loaded
  routes.
- `prompt_routes.detect_prompt_route` and reuse-check consume the composed
  route set; context hydration lists route ids and trigger summaries only.
- Red: a profile route pack must be picked up by `prompt-check` without any
  code change; an invalid pack must fail with a typed error and not poison
  existing routes; bucket placement must be observable in the hydration
  payload (always-inject card present, listed-lazy body absent).

## Track B — Model And Host Independence

### B1. Three-tier model alias catalog

New public data file `docs/model-catalog.json` (schema
`model-catalog-v1`) plus resolver module `model_catalog.py`:

```json
{
  "schema_version": "model-catalog-v1",
  "version": "2026-06-10.initial",
  "observed_at": "2026-06-10",
  "roles": {
    "main_model": {"family": "opus", "purpose": "primary teacher-facing agent"},
    "aux_model": {"family": "haiku", "purpose": "reserved: cheap side tasks (summaries, drafts)"},
    "judge_model": {"family": "sonnet", "purpose": "reserved: independent verification"}
  },
  "families": {
    "opus": {"provider": "anthropic", "concrete": "claude-opus-4-8"},
    "sonnet": {"provider": "anthropic", "concrete": "claude-sonnet-4-6"},
    "haiku": {"provider": "anthropic", "concrete": "claude-haiku-4-5"},
    "gpt-frontier": {"provider": "openai", "concrete": "gpt-5.5"}
  },
  "models": {
    "claude-opus-4-8": {"provider": "anthropic", "status": "active", "notes": "example concrete entry"},
    "claude-sonnet-4-6": {"provider": "anthropic", "status": "active"},
    "claude-haiku-4-5": {"provider": "anthropic", "status": "active"},
    "gpt-5.5": {"provider": "openai", "status": "active", "notes": "proves provider neutrality"}
  }
}
```

- Resolution: role -> family -> concrete, returning the full provenance chain
  (`main_model -> opus -> claude-opus-4-8 -> provider anthropic`). Typed
  errors for dangling aliases, unknown roles, deprecated concretes, and
  cycles.
- Identity semantics adopted from oh-my-pi `packages/catalog/src/identity/`:
  a stdlib-only `parse_model_id()` classifying ids into family/kind/version;
  equivalence grouping with precedence override > bundled > narrow heuristic
  > fallback, and the hard rule that ambiguous families never merge without
  an explicit override entry; a deterministic variant comparator for
  resolving a family to a concrete entry. Invariant: every journal, trace,
  and context payload that names a model records the **concrete** id with
  the alias chain as provenance — never the alias alone.
- Optional `context_promotion_target` field on concrete entries (oh-my-pi
  context-promotion ladder): a larger-context sibling recommended on
  context-pressure signals. This cycle it is advisory only — surfaced by
  doctor and the hydration payload; no automatic switching, and an applied
  recommendation never rewrites the teacher's role defaults.
- Per-profile override file with the same schema may re-point a role or a
  family; repo file stays the public default. Override resolution order:
  profile role > repo role > error (omx three-step order, minus env vars —
  profile state is our env).
- `managed_versions` array records previous catalog versions so a future
  migration can apply the lazycodex rule: rewrite only values that match a
  known managed version, never a hand-edited override.
- CLI verbs under `harness model`: `resolve <role>`, `list`, `validate`.
  Doctor gains a catalog check (dangling/cycle/deprecated-in-use).
- Today's only consumers: context hydration includes a `model_catalog`
  section (role -> concrete chain) so the running agent can state its expected
  staffing; plans and skills reference roles, never concrete ids. The catalog
  performs no model switching while Codex Desktop owns execution.
- Red/green: resolver unit tests (chain, overrides, typed errors), CLI
  contract tests, doctor check tests, docs-contract pin for the schema
  version.

### B2. Host identity as adapter data

New module `hosts.py` defining the host adapter contract and the
`codex_desktop` adapter as its first implementation:

- Adapter fields: `host_id`, `agent_actor`, `runtime_label`,
  `workspace_dirname`, `hook_dialect` (inbound payload keys, outbound
  context/decision shapes), `host_files` (plugin manifest, hooks config
  paths).
- Migrate the hardcoded sites to adapter lookups:
  - `approvals.py` `AGENT_ACTOR` becomes `active_host().agent_actor`
    (self-approval rejection logic unchanged).
  - `context.py` runtime label and `codex-workspace` dirname come from the
    adapter; `build_codex_context` becomes a thin alias of a host-neutral
    `build_host_context` (public CLI surface unchanged).
  - `command_parser.py` adds `--for-host <id>` with `--for-codex` kept as a
    deprecated alias.
  - `doctor.py` host-file checks iterate `active_host().host_files`.
- Host selection: single active host for now (`codex_desktop`), stored as
  data, not branched logic. Future hosts implement the same contract.
- Red: an architecture test (B4) fails while host tokens remain in core
  modules; adapter tests assert byte-identical context output before/after
  the migration (no behavior change this wave).

### B3. Wire harness-event-v1 as the real ingress

- `commands.py` hook path normalizes inbound payloads through
  `harness_events.normalize_event_file` (extended to accept stdin payloads)
  before dispatch; `hook_payloads.py` becomes the codex-dialect reader used
  by the adapter, not by core.
- The gap-analysis P0 hook-contract fixes (native Stop decision contract,
  stop-loop guard, PostCompact correction, PreToolUse gate) land inside the
  codex adapter's outbound dialect so fixing them does not deepen coupling.
  This wave depends on those P0 items and must be sequenced after or together
  with them.
- Red: a synthetic envelope payload (no Codex field names) must drive the
  full hook dispatch in tests; a Codex-dialect payload must produce an
  identical envelope to the equivalent synthetic one.

### B4. Detachability proof

- Architecture contract test `tests/test_host_independence.py`: core modules
  (everything except `hosts.py`, the codex adapter data, bootstrap, and
  explicitly allowlisted doc strings) must contain no host tokens
  (`codex`, `Codex`). Style: the existing docs-contract grep tests.
- Fake-host fixture test: a `tests/fixtures/hosts/fake_host` definition
  drives session-start -> context hydrate -> memory obligation -> closeout
  entirely through harness-event-v1, with its own actor name and workspace
  dirname, and the full flow passes without any Codex dialect. This test is
  the executable answer to "언제든지 뗄 수 있어야 한다".
- Red first: both tests are written before B2/B3 refactors and fail against
  the current tree.

## Track C — Privacy And Self-QA Data Contracts (oh-my-pi absorption)

### C1. Two-mode learner-PII pseudonymization contract

Concretizes gap-roadmap item 36 (previously P2/L with no contract) using the
oh-my-pi `docs/secrets.md` data-contract shape, inverted for learner data:

- A per-profile privacy data file declaring entries as `plain` or `regex`
  with two modes: `reversible` (deterministic same-length placeholder,
  restorable only on owner-facing surfaces — the side panel renderer and
  explicitly-flagged teacher CLI output) and `oneway` (deterministic
  replacement that never round-trips; for data that must not be
  reconstructable from transcripts).
- Application points: every payload that crosses into hydration context,
  trace/audit journals, or any public-repo-bound artifact passes through the
  pseudonymizer after the existing secret/path redaction.
- The reverse map lives only in profile state, is itself redacted from all
  exports, and reversible restoration is a pure local lookup — never an
  inference.
- Red: round-trip test (reversible entry restored on side-panel surface,
  absent everywhere else), one-way stability test (same input, same
  replacement, no reverse map entry), export-scrub test (reverse map never
  leaves profile state).
- Scope note: this wave ships the contract and the pseudonymizer seam, not
  retroactive rewriting of existing journals.

### C2. Consent-gated harness self-QA ledger

Strengthens gap-roadmap item 19 (bounded diagnostics) with the oh-my-pi
`report_tool_issue` + install-id pattern, fully local:

- Hooks and CLI append harness anomalies (contract violations, malformed
  payloads, unexpected host behavior, gate denials that look like bugs) to a
  bounded local append-only ledger whose schema structurally excludes
  learner data and prompt text (ids, error codes, redacted summaries only).
- One-time consent state (`unset -> granted | denied`) controls whether the
  ledger is even written; the teacher reviews and clears it from doctor
  output (and later the side panel). No remote endpoint exists.
- A per-install id is created with exclusive-create semantics
  (`os.open(..., O_CREAT | O_EXCL)`, owner-only permissions) for dedup if a
  report is ever manually shared.
- Red: schema-rejection test (a learner-name field cannot be written),
  consent-gate test (no writes while unset/denied), bounded-size test
  (rotation at the cap), exclusive-create race test.

## Development Method, Test Plan, Success And Failure Criteria

Development method:

- Wave order: A0 and B1 first (independent of each other), then A1-A2 in
  parallel with B2, then A3-A4 in parallel with B3, then B4 last.
- Every task is red -> green TDD with captured transcripts under the local
  evidence convention, and goal-ledger entries with `qa_verifier_status`
  verified by an independent QA pass, per repo convention.
- Implementation and QA verification are separate roles per goal; no goal is
  marked complete by its implementer alone.

Test plan:

- Unit contract tests per new module (`side_panel_blocks.py`,
  `model_catalog.py`, `hosts.py`).
- Subprocess CLI contract tests for every new verb (template:
  `tests/test_agent_tools_lifecycle_cli.py`).
- Privacy tests extended: quarantine directory patterns enter `.gitignore`
  coverage assertions; telemetry payloads asserted free of learner fields.
- Architecture grep test plus fake-host end-to-end fixture test (B4).
- Full `uv run pytest`, `ruff check` (select=ALL), `basedpyright` green at
  every wave boundary; no existing test may be deleted or weakened to pass.

Success criteria (all must hold):

- `python -m chat_lms_agent harness model resolve main_model --json` returns
  status PASS with the full provenance chain, and a profile override
  re-points a role without touching the repo file.
- A block can travel scaffold -> preview -> promote only with test evidence,
  a `panel:<id>` memory record, and a consumed teacher approval; an
  unapproved promote returns `NEEDS_APPROVAL`; a draft block never renders
  through the production path.
- A new daily route ships as a JSON pack (repo or profile) with zero code
  change and is visible to `prompt-check` and reuse-check.
- `tests/test_host_independence.py` and the fake-host end-to-end test are
  green; context output for the codex host is byte-identical across the B2
  refactor.
- Every model mention in journals/trace/context records the concrete id
  with alias provenance; resolving a family with two concrete candidates is
  deterministic and covered by a comparator test.
- A reversible privacy entry renders restored on the side-panel surface and
  pseudonymized everywhere else; the reverse map never appears in any
  export; the self-QA ledger refuses learner-data fields at schema level
  and writes nothing without granted consent.
- All pre-existing tests remain green; runtime dependencies remain zero.

Failure criteria (any one fails the wave):

- Any LLM call, provider SDK, embedding, or network dependency enters the
  repo.
- The production side-panel loader can reach unpromoted or quarantine HTML,
  or `no_from_scratch` assertions are weakened.
- Any promotion path completes without an approval-ledger consumption.
- Host tokens remain in core modules after B2, or the harness writes to
  host-owned config files.
- Catalog resolution silently falls back instead of returning typed errors
  for dangling/cycle/deprecated references.

## Roadmap Mapping

- A0 = gap-analysis roadmap items 7 (tool store unification) and 25
  (evidence-gated transitions).
- A3 telemetry aligns with item 23 (memory telemetry trait); A4 = item 24
  as revised by item 43 (bucket ingestion).
- A1 closing-report contract = item 47.
- B1 identity/equivalence semantics and `context_promotion_target` = item
  42.
- C1 = item 44 (elevates and concretizes item 36); C2 = item 45 (extends
  item 19).
- B3 depends on P0 items 1-4 (Stop decision contract, stop-loop guard,
  PostCompact correction, PreToolUse gate — item 41 revises the PreToolUse
  gate into the approval-tier decision table) and must not ship before
  them.
- B1 and C2 have no dependencies and can start immediately alongside A0; C1
  slots after the P0 context-diet wave so the pseudonymizer seam composes
  with the tiered hydration path.

Wave order incorporating Track C: A0 and B1 first, then A1-A2 with B2 and
C2, then A3-A4 with B3 and C1, then B4 last.
