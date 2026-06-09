# Harness V4 OSS Reference Expansion Plan

## Purpose

V4 strengthens the committed V3 harness by applying the user's "core principles" and current OSS agent ecosystem research.

The target remains unchanged:

```text
Codex Desktop today
  -> Chat LMS reusable harness core
    -> private profile state, academy DB, memory, tools, audit, approvals, side-panel contracts
Future standalone desktop or Web SaaS later
  -> same reusable harness core through a different host adapter
```

V4 must not turn Chat LMS Agent into a replacement model runtime. It must make the current Codex Desktop harness better at remembering, discovering, reusing, auditing, and transitioning.

## Plain-Language Model

The harness should work like a teacher operations workshop.

- `AGENTS.md` is the workshop rulebook.
- Agent Skills are labeled drawers for repeatable jobs.
- CLI tools are the real instruments, not one-off hand work.
- MCP is the future universal socket so other hosts can discover the same instruments.
- Context offload is the labeled storage shelf: large raw outputs stay retrievable by id instead of being dumped into the working context.
- Trace, audit, approval, and memory are the workshop logbook.
- Context maps are the index on the wall, so the agent does not rummage through every cabinet.
- Verifier receipts are the closing stamp: risky or substantial work is not "done" until an independent check passes.

The agent still has freedom. The difference is that it starts inside a well-labeled workshop instead of an empty room.

## User Principles Applied

- Simplicity: every new capability must say where truth lives, where generated views live, how failure is detected, and how recovery happens.
- Compound workflow: repeated work must become a CLI, skill, template, checklist, or memory obligation.
- Reuse before build: before creating a new tool, the agent must check existing repo commands, existing skills, existing OSS, and existing host features.
- Documented truth and SSoT: canonical docs and private runtime truth must be clearly separated from caches, summaries, indexes, and views.
- Agentic flexibility: the agent can proceed on low-risk reversible assumptions, but must stop for human approval on private data, external writes, destructive operations, payments, permissions, deployments, and canonical truth changes.
- Context hygiene: every reference must include source, freshness, scope, priority, canonical/deprecated status, and "must not copy" notes.
- Feedback loop: failures and repeated confusion must become tests, doctor checks, CLI affordances, or documented failure patterns.

## Current V3 Baseline

Already implemented and committed in V3:

- host-neutral event envelope;
- trace and audit ledgers;
- human approval ledger;
- academy DB operations, reports, backups, migrations, import planning;
- memory draft/apply/compact/archive/session-summary lifecycle;
- side-panel policy bridge;
- context hydration, doctor, closeout, bootstrap integration;
- public repo vs private profile boundary.

V4 does not replace these. It adds an OSS-informed discovery, reuse, interoperability, and context-quality layer on top.

## External Reference Decision Matrix

Observed date: 2026-06-09.

Star counts and social popularity are freshness-sensitive signals. They are not used as architecture truth by themselves.

Important terminology:

- `Direct use now` means Chat LMS adopts the convention or file layout in this repo now. It does not automatically mean adding a new runtime dependency.
- `Candidate next` means the dependency or server surface may be implemented after a separate dependency/privacy review.
- `Structural reference` means source-pinned architecture inspiration only: adopted trait, local mapping, and must-not-copy rule. No source copying and no runtime coupling.

| Reference | Use Decision | What To Adopt | What Not To Copy |
| --- | --- | --- | --- |
| AGENTS.md | Direct use now | Canonical predictable agent instructions, nested instruction scope, cross-agent compatibility. | Do not put private profile data or volatile runtime state in public AGENTS.md. |
| Agent Skills | Direct use now | `SKILL.md` + optional `scripts/`, `references/`, `assets/`; progressive disclosure; reusable workflow packaging. | Do not create huge always-loaded skill files or hidden scripts without validation. |
| MCP | Direct-use candidate next | Read-only discovery server for tool registry, memory context, academy DB schema, side-panel catalog. | Do not expose write tools by default; no private data leak through public repo. |
| OpenCode | Structural reference | Multiple surfaces: terminal, desktop, IDE; plan/read-only mode vs build/full-access mode. | Do not replace Codex Desktop runtime or copy OpenCode internals. |
| Aider | Structural reference | Repo-map-like context map; Git-style receipts and rollback-friendly workflow. | Do not embed Aider as the editor/runtime. |
| OpenAI Agents SDK | Structural reference | Tracing, sessions/resume, tools, handoffs, guardrails, human-in-loop vocabulary. | Do not add a model loop/provider router while Codex Desktop is the host. |
| LangGraph | Future dependency candidate | Durable execution, checkpointing, human-in-loop, long-running workflow concepts. | Do not add graph orchestration until standalone/SaaS needs it. |
| OpenHands | Structural reference | SDK/CLI/local GUI/cloud surface split; file-based agent roles. | Do not replace the current host or import a full autonomous coding platform. |
| SWE-agent / mini-SWE-agent | Structural reference | Linear trajectories, inspectable run logs, simplicity discipline. | Do not use coding-agent benchmarks as Chat LMS product success metrics. |
| Letta | Memory reference | Stateful agents, memory blocks, skills/subagents, local terminal memory concepts. | Do not make cloud memory or self-improving behavior the default. |
| Mem0 | Memory reference, optional later | Multi-level memory, add-only extraction, hybrid retrieval, temporal retrieval concepts. | Do not add embeddings/cloud/API keys to private learner ops by default. |
| Langfuse | Future observability candidate | Traces, sessions, observations, async export, self-hostable observability. | Do not require an observability server for local Codex Desktop use. |
| Temporal | Future durable workflow candidate | Durable tool execution and crash-resumable long workflows. | Do not add infrastructure before standalone/SaaS needs queues and workers. |
| PydanticAI | Reference only | Type-first structured outputs and dependency-injected tools as design inspiration. | Do not replace existing dependency-light CLI core. |
| smolagents | Reference only | Keep agent/tool abstractions small and understandable. | Do not add a code-agent framework for academy operations. |
| Headroom | Candidate-next, concept now | Reversible context compression/offload, local originals, retrieve-by-id, context budget metrics, MCP-compatible compression tool shape. | Do not wrap/proxy Codex Desktop traffic by default; do not compress away audit truth; do not send private data through external services. |
| TencentDB Agent Memory | Structural memory reference | Layered/symbolic memory: raw refs, step summaries, lightweight canvas; L0 conversation, L1 atoms, L2 scenarios, L3 persona. | Do not import OpenClaw/Hermes gateway patches, default model endpoints, Docker sidecars, or open HTTP services into local teacher ops. |
| roach-pi | Structural harness reference | Verifier-gated durable goal runtime, evidence/blocker receipts, lazy MCP discovery, workspace memory, nested AGENTS.md, git-aware search/LSP affordances. | Do not replace Codex Desktop or add a second coding-agent runtime. |

## Source Registry To Add

Create `docs/oss-reference-registry.md` as the canonical OSS reference registry.

Each entry must include:

- `id`
- `source_url`
- `pinned_head_sha`
- `observed_at`
- `license`
- `popularity_signal`
- `local_problem_matched`
- `adoption_status`: `direct-now`, `candidate-next`, `reference-only`, `rejected`
- `local_mapping`
- `must_not_copy`
- `privacy_boundary`
- `freshness_note`

This registry becomes the SSoT for external references. Other docs may summarize it but must not fork decisions.

`docs/golden-standards.md` should become a curated summary that points to this registry. It must not be the second source of truth.

Additional user-supplied references observed on 2026-06-09:

- `chopratejas/headroom` at `9579567b7dae31b226a634b7f63a988253fc03b8`
- `TencentCloud/TencentDB-Agent-Memory` at `f92b10259b8b5780f8b0056b5c8526fc98f5646f`
- `tmdgusya/roach-pi` at `a2da093fd7cd00d1204b6c7eabc50245f71cde98`

## Metis Review Corrections

The Metis gap review found several plan risks. V4 resolves them as follows:

- AGENTS.md and Agent Skills are "direct use" as conventions/layouts only. This does not create a new runtime.
- External references must live in one SSoT file: `docs/oss-reference-registry.md`.
- MCP starts as a read-only, optional, disabled-by-default adapter. If implemented, it uses explicit `--profile-root`, `--read-only`, and `stdio` first.
- MCP may expose private profile summaries only after redaction tests. It must not expose raw learner data, secrets, or generated reports.
- Trace/audit storage must be reconciled before adding new trace features. Current implementation writes per-record `.json` files and reads `.json` plus `.jsonl`; V4 should document that as canonical unless a later migration deliberately changes it.
- Docs contract tests must cover external reference schema and must fail on mojibake/corrupted canonical names.
- Retention and lock defaults from V3 must be made concrete before expanding background/discovery surfaces.
- Approval risk fields must be phased deliberately; do not imply TTL/risk/backup fields are complete until code and tests support them.
- Headroom-style compression is allowed only as reversible offload or optional evaluation. The default Codex Desktop path must not route model traffic through a proxy/wrapper.
- TencentDB-style memory layering should strengthen the local memory model, but HTTP gateways, Docker sidecars, and OpenClaw/Hermes patches are out of scope for local teacher operations.
- roach-pi-style verifier gating should strengthen completion criteria, but it must use Chat LMS trace/audit/QA surfaces rather than replacing the host runtime.
- roach-pi's MCP proxy pattern is reinterpreted as lazy read-only discovery for Chat LMS. V4 must not add a write-capable MCP proxy.
- New external references must be measurable through registry/docs/tests first. Runtime dependency adoption requires a separate implementation wave and dependency review.

Default storage decision for V4:

- Write trace/audit records as per-record JSON files under the profile state directory.
- Keep JSONL support as backwards-compatible read/import/export format.
- If JSONL append-only storage is desired later, create a separate migration plan.

## V4 Work Waves

### Wave 0: Repair Context Truth

Goal:

- Clean up broken Korean/encoding artifacts in public docs.
- Add `docs/oss-reference-registry.md`.
- Mark `docs/golden-standards.md` as a summary that points to the registry, not a competing truth source.
- Align trace/audit storage docs with the actual per-record JSON implementation.
- Define default retention thresholds and lock expectations in public docs.

Files:

- `docs/oss-reference-registry.md`
- `docs/golden-standards.md`
- `docs/terminology.md`
- `docs/runtime-boundary.md`
- `tests/test_repo_privacy.py`
- `tests/test_docs_contract.py`

Acceptance:

- No mojibake remains in golden-standard names or side-panel terminology.
- Every external reference has a source URL, observed date, adoption status, and must-not-copy rule.
- `tests/test_docs_contract.py` compiles and validates the registry schema.
- Trace/audit docs say the current canonical write format is per-record JSON, with JSONL as compatible read/export format.
- Retention has a concrete default, for example 90 days or 10 MB per ledger directory, whichever comes first.
- Shared profile-state writes name the lock discipline expected by implementation.
- Public repo privacy tests still pass.

Failure:

- Multiple docs disagree on which OSS references are direct dependencies.
- A public doc implies private runtime data or external OSS internals are copied.
- Docs tests preserve corrupted text as the expected value.

### Wave 1: Reuse-Before-Build Gate

Goal:

- Prevent agents from inventing new one-off tools before checking existing commands, skills, host features, and OSS candidates.

Implementation direction:

- Extend agent-tool proposal schema with `reuse_review`.
- Require the proposal to document:
  - existing Chat LMS command checked;
  - existing skill checked;
  - existing side-panel block checked when UI is involved;
  - OSS/API/library candidate checked;
  - reason direct build is still justified.
- Add a lightweight CLI affordance:

```text
python -m chat_lms_agent agent-tools reuse-check --intent <text> --json
```

Acceptance:

- `agent-tools validate` rejects proposals missing `reuse_review`.
- `agent-tools reuse-check` returns matching existing tools/skills/docs before scaffolding.
- Tests cover "existing tool found", "OSS candidate noted", and "custom build justified".

Failure:

- A new tool can be registered without proving reuse was checked.
- The gate blocks small reversible work that should remain agentically flexible.

### Wave 2: Skills As Reusable Workflow Drawers

Goal:

- Align Chat LMS skills with Agent Skills conventions so future Codex, Claude, OpenCode, or standalone hosts can reuse them.

Implementation direction:

- Validate local skill folders for:
  - required `SKILL.md`;
  - frontmatter `name` and `description`;
  - focused optional `scripts/`, `references/`, `assets/`;
  - no private data;
  - no unbounded always-loaded context.
- Add or extend a command:

```text
python -m chat_lms_agent skills list --json
python -m chat_lms_agent skills validate --json
```

Acceptance:

- Chat LMS skills are discoverable by name, purpose, and trigger.
- Invalid or oversized skill definitions fail validation.
- Skill validation is included in `doctor`.

Failure:

- Skills become another dumping ground for long, stale instructions.
- A skill script performs writes without an explicit policy/approval surface.

### Wave 3: Read-Only MCP Discovery Adapter

Goal:

- Prepare the transition path where other hosts can discover Chat LMS capabilities without copying Codex-specific internals.

Implementation direction:

- Treat this as a later wave after source registry, skill validation, context map, and trace inspector are stable.
- Add an optional extra for MCP dependencies, not a default dependency.
- Keep MCP disabled by default.
- Add read-only command:

```text
python -m chat_lms_agent mcp serve --profile-root <root> --read-only --transport stdio
```

Expose only read-only resources first:

- public tool registry;
- public side-panel catalog;
- private profile context summary, redacted;
- academy DB schema and saved query names;
- memory keys and summaries, redacted;
- approval/audit/trace indexes, redacted.

roach-pi reference boundary:

- Adopt the lazy discovery principle: avoid flooding context with every possible tool definition.
- Use one compact discovery surface that lists or fetches tools/resources only when asked.
- Do not adopt a write-capable proxy.
- Do not store OAuth credentials or external server state in the public repo.

Acceptance:

- MCP server cannot mutate state.
- MCP command returns explicit JSON errors for missing optional dependency, missing profile root, redaction failure, malformed registry, or attempted write tool access.
- Redaction tests cover private profile paths, learner-like data, and secrets.
- The adapter reads from canonical core contracts, not from Codex hook internals.
- Public repo development mode exposes public metadata only.

Failure:

- MCP exposes raw private learner records.
- MCP becomes a second implementation of DB/memory/tool logic.
- MCP starts an always-on server or network listener during ordinary Codex Desktop use.

### Wave 4: Context Map

Goal:

- Give new sessions a compact, current map of available tools, schemas, memory keys, side-panel blocks, docs, and pending obligations.
- Incorporate git-aware ranking/frecency principles from roach-pi's search layer without replacing the repo's normal search tools.

Implementation direction:

- Add a generated-but-not-truth context map inspired by Aider's repo map:

```text
python -m chat_lms_agent context map build --profile-root <root> --json
python -m chat_lms_agent context map show --profile-root <root> --json
```

Rules:

- The map is regenerated from canonical docs, CLI registry, schemas, and private profile state.
- The map never becomes truth.
- If missing/stale, `context hydrate` can rebuild it.

Acceptance:

- A fresh session can list relevant commands and memory obligations without scanning from scratch.
- Stale maps are detected and rebuilt.
- Tests prove canonical source changes update the map.

Failure:

- The map is manually edited as truth.
- The map contains private raw data instead of redacted summaries.

### Wave 4A: Reversible Context Offload

Goal:

- Stop huge tool outputs, DB query results, logs, and report drafts from bloating new-session context while preserving exact originals.

Reference mapping:

- Headroom contributes the reversible compression/offload idea: compressed summaries in context, original content retrievable on demand.
- TencentDB Agent Memory contributes the layered short-term context idea: raw refs at the bottom, step summaries in the middle, lightweight top-level canvas/map.

Implementation direction:

- Start with docs, tests, and synthetic fixtures before any dependency adoption.
- Headroom may be evaluated as an optional candidate only after the local offload contract is clear.
- Add local-only offload commands:

```text
python -m chat_lms_agent context offload put --profile-root <root> --kind <tool_output|db_result|log|report_draft> --from <path> --json
python -m chat_lms_agent context offload get --profile-root <root> --ref <offload-id> --json
python -m chat_lms_agent context budget show --profile-root <root> --json
```

Rules:

- Originals are stored in private profile state, never public repo.
- Summaries are caches/views, not truth.
- Every summary includes a pointer to the exact original.
- Every original stores a content hash so retrieval integrity can be verified.
- Offloaded private data must be redacted before appearing in public docs, traces, or side-panel payloads.
- No default proxy/wrapper around Codex Desktop or model traffic.
- No default Headroom dependency. If evaluated, use synthetic fixtures first and keep it disabled by default.

Acceptance:

- A large synthetic tool output can be offloaded, summarized, listed, and retrieved exactly.
- The retrieved original hash matches the stored hash.
- Context hydration can include the compact summary plus `offload_id`, not raw content.
- Redaction tests cover private paths, learner-like names, and secrets.
- Missing original content is reported as a recoverable integrity error.
- Any compression benchmark reports both token savings and answer/regression parity; token savings alone cannot pass the feature.

Failure:

- Compression deletes or mutates the original.
- The agent treats a compressed summary as canonical truth.
- Model/API traffic is routed through a proxy without explicit user approval.
- A compression/offload tool is enabled for real private profile data before synthetic privacy tests pass.

### Wave 5: Trajectory Inspector

Goal:

- Make agent runs inspectable like SWE-agent trajectories and OpenAI/Langfuse-style traces.
- Reconcile trace storage reality before expanding inspection.

Implementation direction:

- Add export/view commands:

```text
python -m chat_lms_agent trace export --profile-root <root> --format trajectory --json
python -m chat_lms_agent trace inspect --profile-root <root> --id <trace-id> --json
```

The trajectory view should show:

- user intent;
- chosen tool;
- command args, redacted;
- result status;
- approval checkpoint;
- memory/audit effects;
- next-session obligations.

Storage rule:

- Read from current per-record JSON trace/audit directories.
- Support JSONL only as import/export/compatibility.
- Do not introduce a second canonical trace ledger.

Acceptance:

- Every risky or state-changing operation has an inspectable path from request to effect.
- Failed operations show where recovery should start.
- Tests cover redaction and causal ordering.

Failure:

- Trace logs are just noise and do not explain what changed.
- Inspector requires opening raw JSONL by hand.

### Wave 6: Memory Architecture Hardening

Goal:

- Use Letta/Mem0 concepts without giving up local, reviewable, private control.
- Add TencentDB Agent Memory's core lesson: memory must not be flat. It should be layered, symbolic, and drill-down capable.

Implementation direction:

- Keep local profile memory as the default SSoT.
- Map TencentDB Agent Memory's L0-L3 idea into the existing Chat LMS memory taxonomy instead of creating a competing truth model:

| TencentDB Layer | Chat LMS Mapping | Hydration Rule |
| --- | --- | --- |
| L0 Conversation/raw source | `conversation_ref` or `offload_id` | Not hydratable by default; retrieve only on demand. |
| L1 Atom | reviewed `atom`, `tool_knowledge`, or `failure_pattern` | Hydratable when relevant and current. |
| L2 Scenario | `scenario` / recurring workflow memory | Hydratable as a compact group. |
| L3 Persona | `user_preference`, `academy_policy`, `persona_or_policy` | Hydratable only when current and reviewed. |
| Short-term canvas | generated `session_summary` / `context map` | Generated view, not truth. |

- Add long-term memory levels:
  - `conversation_ref`: pointer to raw/private source, not hydratable by default;
  - `atom`: small reviewed fact;
  - `scenario`: grouped workflow or recurring situation;
  - `persona_or_policy`: stable preference, academy policy, or teacher operating principle;
  - `failure_pattern`: repeated error with prevention rule;
  - `tool_knowledge`: reusable command/tool knowledge.
- Add operational memory categories:
  - `user_preference`
  - `academy_policy`
  - `profile_state`
  - `session_summary`
  - `tool_knowledge`
  - `failure_pattern`
- Make most memory changes draft-first and add-only until approved.
- Add temporal fields so current vs historical state is explicit.
- Add drill-down pointers from summaries to source refs or offload ids.
- Consider a lightweight Mermaid/state-canvas style top layer for session summaries if it stays generated-from-truth.

Acceptance:

- New sessions can retrieve current tool knowledge and academy policy without raw history.
- Historical facts do not silently override current facts.
- Memory apply requires review for canonical changes.
- L0/raw source references stay private and retrievable, but are not automatically injected into context.
- L3/persona/policy memories require review before becoming current canonical memory.

Failure:

- Embedding/vector memory becomes required for basic local operations.
- The agent can silently overwrite canonical memory.
- Flat vector/log storage becomes the only recall strategy.

### Wave 7: Host Adapter Contract

Goal:

- Keep Codex Desktop as the current host while making future desktop/Web SaaS transition cheap.

Implementation direction:

- Document and test a `HostAdapter` contract:
  - `codex_desktop`
  - future `standalone_desktop`
  - future `web_saas`
- Adapter responsibilities:
  - receive user events;
  - call core commands;
  - render side-panel payloads;
  - submit human approvals;
  - surface trace/audit/status.

Acceptance:

- Core DB/memory/tool/audit logic does not import Codex-specific hook payloads.
- Codex hook adapter is one adapter, not the whole product.
- Future hosts can reuse the same JSON contracts.

Failure:

- Codex Desktop behavior leaks into core storage schemas.
- Standalone/SaaS requires rewriting the DB/memory/tool core.

### Wave 8: Approval And Risk Taxonomy

Goal:

- Make human checkpoints precise without choking normal low-risk work.

Implementation direction:

- Add risk classes:
  - `read_only`
  - `draft_only`
  - `local_reversible_write`
  - `canonical_write`
  - `private_data_write`
  - `external_write`
  - `destructive`
- Map risk classes to approval requirements.
- Approval records must include human actor, reason, diff/plan, rollback note, expiry, and trace link.
- Add these fields in schema-versioned phases so existing V3 approvals remain readable.

Acceptance:

- Low-risk reversible operations are not over-blocked.
- Private data, canonical writes, destructive actions, and external writes cannot proceed without human approval.
- Tests cover denied, expired, reused, and wrong-actor approvals.
- Backward-compatible reading of existing approval records is tested.

Failure:

- The agent self-approves risky work.
- Approval becomes a vague checkbox without a visible effect summary.

### Wave 9: Verifier-Gated Goal Runtime

Goal:

- Make substantial agentic work durable and completion-proof, using roach-pi's goal/verifier idea without replacing Codex Desktop.

Implementation direction:

- Treat this as a verifier receipt pattern over existing Chat LMS trace/audit/doctor/closeout surfaces.
- Do not add a pi-style subagent process manager or a second orchestrator.
- Add a host-neutral goal record under private profile state:
  - `goal_id`
  - `objective`
  - `subgoals`
  - `evidence_refs`
  - `blockers`
  - `approval_refs`
  - `trace_refs`
  - `qa_verifier_status`
  - `next_action`
- Add commands:

```text
python -m chat_lms_agent goal status --profile-root <root> --json
python -m chat_lms_agent goal evidence add --profile-root <root> --goal-id <id> --from <path> --json
python -m chat_lms_agent goal verify --profile-root <root> --goal-id <id> --json
```

Rules:

- A goal involving code, DB schema, memory architecture, approvals, or side-panel contracts is not complete until QA/verifier status is `PASS`.
- Verifier evidence must reference tests, command transcripts, trace/audit ids, or explicit human approval.
- Blocked status requires a concrete repeated blocker, not ordinary uncertainty.
- Parallel/chain/async subagent ideas remain reference-only unless a later Codex Desktop host adapter explicitly supports them.

Acceptance:

- `goal status` shows active subgoals, blockers, evidence, and next action.
- `goal verify` fails when tests/evidence are missing.
- Completion is prevented unless verifier status is `PASS`.
- Existing closeout can read goal obligations.
- Goal records link back to trace/audit rather than creating a separate truth silo.

Failure:

- The goal runtime becomes a second task manager disconnected from trace/audit/memory.
- The verifier is just a text note with no evidence refs.
- The plan introduces an alternate coding-agent runtime.

### Wave 10: Future Durable Workflow Decision Gate

Goal:

- Decide when to adopt LangGraph, Temporal, AutoGen, or another durable workflow layer later.

Decision gate:

Adopt a workflow engine only if at least two are true:

- standalone/SaaS host is active;
- multi-user operations exist;
- workflows must survive app/server restarts;
- background jobs require retries and scheduling;
- approvals can pause for hours/days;
- external adapters become real, not dry-run only.

Acceptance:

- Before the gate, keep simple local CLI/state contracts.
- After the gate, choose one durable engine through a new source-pinned plan.

Failure:

- V4 adds a graph/workflow server before the current harness needs one.

### Wave 11: Verification

Required tests:

```text
uv run pytest tests/test_package_import.py tests/test_repo_privacy.py -q
uv run pytest tests/test_agent_tools*.py tests/test_context*.py tests/test_memory*.py tests/test_trace*.py -q
```

Required QA transcripts:

- `agent-tools reuse-check`
- `skills validate`
- `context map build/show`
- `context offload put/get` and `context budget show`
- `mcp serve` read-only smoke, if implemented in that loop
- `trace export/inspect`
- `goal status/evidence/verify`
- approval denied/expired/reused cases

Final acceptance:

- The harness starts each session with a compact map of existing capabilities.
- Repeated work has a path to become a skill or CLI.
- New tool proposals prove reuse was checked.
- Memory updates are reviewable and durable.
- External OSS references are source-pinned and classified.
- New reference tests prove Headroom/TencentDB Agent Memory/roach-pi are registry entries only unless a later dependency review explicitly changes their status.
- Public repo remains publish-safe.

## Implementation Order

Recommended execution:

1. Wave 0: fix reference truth and encoding artifacts.
2. Wave 1: add reuse-before-build gate.
3. Wave 2: validate skills as reusable workflow drawers.
4. Wave 4: build context map.
5. Wave 4A: add reversible context offload.
6. Wave 5: add trajectory inspector.
7. Wave 6: harden layered memory and temporal fields.
8. Wave 8: refine approval/risk taxonomy.
9. Wave 9: add verifier-gated goal runtime if not already covered by closeout.
10. Wave 3: add MCP read-only adapter only after the above contracts are stable.
11. Wave 7 and Wave 10: keep as transition-readiness contracts unless standalone work begins.
12. Wave 11: run full verification and update docs.

## Non-Goals

- No external writes.
- No real learner data in public repo.
- No cloud memory default.
- No replacement LLM loop.
- No provider router.
- No default context proxy/wrapper around Codex Desktop.
- No lossy-only compression for private operational truth.
- No graph orchestrator until the decision gate is met.
- No Docker/HTTP gateway sidecars for local teacher memory by default.
- No write-capable MCP proxy by default.
- No alternate subagent process manager inside Chat LMS V4.
- No copying private Hermes, OMC, OMX, lazycodex, or gajae-code internals.
- No copying external OSS source without license review and a specific direct-use decision.

## Summary

V4 should make the harness more agentic by making its tools easier to discover and reuse.

This is not restraint for restraint's sake. The agent gets more freedom because it gets a dependable map, labeled tools, clear memory, safe approvals, and an audit trail that survives new sessions.
