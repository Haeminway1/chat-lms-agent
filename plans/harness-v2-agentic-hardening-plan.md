# Harness V2 Agentic Hardening Plan

## TL;DR
> **Summary**: Finish the agentic harness by making Codex sessions automatically discover tools, enforce memory, manage tool lifecycles, and operate the academy DB through reusable CLI packs instead of ad-hoc agent work.
> **Deliverables**:
> - Full hook lifecycle: `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PostCompact`, `Stop`.
> - Automatic memory draft/update/verify workflow.
> - Complete `agent-tools` lifecycle CLI.
> - Real `academy-db` CLI pack for schema, migrations, imports, queries, reports, backup, and restore.
> - Public/private boundary enforcement for every new runtime artifact.
> **Effort**: Large
> **Parallel**: YES - 5 implementation waves plus final verification
> **Critical Path**: Task 0 -> Task 1 -> Task 4 -> Task 5 -> Task 10 -> Task 13 -> Task 14 -> Final Verification

## Context
### Original Request
The user asked for a second-phase plan for the remaining hardening needed before the system can be called a strong self-managing agentic harness. The four named areas are hook lifecycle integration, automatic memory update, tool lifecycle CLI, and the real academy DB tool pack.

### Interview Summary
- The agent should feel freer because it has durable tools, not because it improvises every workflow.
- Chat LMS Agent is optimized for academy/class operations and must avoid rebuilding DBs from scratch every session.
- New tools, DB schemas, hooks, and side-panel contracts must create structured durable memory/decision records.
- Public repo code expands the harness boundary; real runtime data stays in private profile workspaces.

### Current Baseline
- `agent-tools list --json` and `agent-tools validate --from <path> --json` exist in the current working tree.
- `context hydrate --for-codex --json` exposes `agent_tools`, `tool_registry`, `memory_policy`, and `side_panel`.
- `doctor --json` exposes an `agent_tools` readiness check.
- Hook parsing accepts `--changed-files` and `--memory-updated`, but `hooks/hooks.json` only registers `SessionStart` and `Stop`.
- `academy-db` is currently a registry entry, not a real CLI pack.

### Metis Review (gaps addressed)
- V2 explicitly supersedes the v1 `academy-db` registry-only scope: academy DB becomes a real private-profile CLI pack, still with public-safe fixtures only.
- Windows QA uses `scripts/qa/capture-command.ps1` transcripts when tmux is unavailable; coding and QA agents remain required during execution.
- Hooks must be both implemented and registered in `hooks/hooks.json` for all five lifecycle events.
- Memory automation means reviewable draft generation by default, not silent durable writes.
- V2 command flags are fixed in this plan to prevent drift: hook changes use `--changed-files`, memory drafts use `memory draft`, and academy DB commands use the `academy-db` namespace.
- The v2 managed-path set must cover hooks, parser, context, doctor, memory, tool lifecycle, academy DB modules, docs, and bootstrap so closeout cannot miss harness changes.

### Plan Reviewer Review (ordering addressed)
- `commands.py` is already the central dispatcher and near the point where more inline logic would make v2 fragile. V2 starts with shared CLI IO/options helpers before adding new behavior.
- Hook stdin parsing is a hard prerequisite for lifecycle registration because real Codex hooks pass event payloads through stdin.
- Academy DB starts with public-safe schema/query/report contracts before migration/import/report/backup features.
- If scope must shrink during execution, postpone DB maintenance/report polish and bootstrap delegation, but do not postpone hook stdin parsing, full hook registration, memory draft schema, or minimal `academy-db spec/init/query`.

## Work Objectives
### Core Objective
Create a deterministic, public-safe harness that gives every new Codex session a durable, queryable, and enforceable tool/memory/DB operating layer.

### Deliverables
- Hook lifecycle commands and hook payload parser.
- Memory obligation engine with draft/update/verify/apply workflows.
- Tool lifecycle CLI with scaffold/register/promote/deprecate/explain/doctor/run-guidance.
- Academy DB CLI pack with schema registry, migrations, imports, named queries, reports, backup, restore, and doctor.
- QA evidence plan that uses PowerShell CLI transcripts on Windows.

### Definition of Done
- `uv run pytest -q` passes.
- `uv run ruff check src tests` passes.
- `uv run basedpyright src` passes.
- `uv run python -m chat_lms_agent hook session-start --json` emits hydration context with `agent_tools`, `tool_registry`, `memory_policy`, `academy_db`, and `side_panel`.
- `uv run python -m chat_lms_agent memory draft --for tool-change --changed-files src/chat_lms_agent/agent_tools.py --json` emits a structured draft obligation.
- `uv run python -m chat_lms_agent agent-tools scaffold --from tests/fixtures/agent_tools/valid-tool-request.json --json` creates a draft without activating unsafe code.
- `uv run python -m chat_lms_agent academy-db spec --json` and `academy-db init --profile-root <temp> --json` work without writing DB artifacts into the public repo.
- Every task has RED/GREEN test evidence and a PowerShell CLI transcript.

### Must Have
- Hook commands parse stdin payloads and tolerate malformed payloads without tracebacks.
- Memory drafts use fixed schemas and are machine-readable.
- Tool lifecycle requires `command_contract`, `memory_obligation`, `safety_boundary`, and `test_contract`.
- Academy DB writes require an explicit private/temp profile root.
- Generated DB files, reports, backups, logs, and runtime memory remain ignored and outside public source control.
- Existing `tool`, `memory`, `context`, `doctor`, `hook`, `side-panel`, and `agent-tools` commands remain backward compatible.

### Must NOT Have
- No real learner records, private reports, DB files, logs, backups, saved secrets, or private paths in public repo.
- No external writes, credential mutation, or destructive local changes.
- No auto-activation of arbitrary generated Python modules.
- No agent-owned side-panel HTML/CSS generation.
- No runtime behavior embedded in large PowerShell scripts when a Python CLI command can own it.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: TDD with pytest. Every production task begins with RED tests.
- Static gate: `uv run ruff check src tests` and `uv run basedpyright src`.
- Manual QA channel: PowerShell CLI transcript because this Windows Codex Desktop runtime has no tmux.
- Evidence path: `evidence/harness-v2/task-{N}-{slug}.txt`.
- Privacy gate: `uv run pytest tests/test_repo_privacy.py -q` and explicit scan for DB/report/log/private path artifacts.

## Execution Strategy
### Parallel Execution Waves
Wave 1: shared CLI IO/options foundation, hook payload/parser foundation, memory schema foundation, runtime artifact boundary, academy DB contract foundation.
Wave 2: hook lifecycle registration, memory draft/update workflow, tool lifecycle proposal model.
Wave 3: tool lifecycle CLI, academy DB schema/init/query foundation, context hydration expansion.
Wave 4: academy DB migrations/import/report/backup/restore, closeout enforcement, bootstrap delegation.
Wave 5: doctor/full QA/review hardening and cleanup.

### Dependency Matrix
| Task | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 0. Shared CLI IO/options split | none | 1, 4, 5, 8, 12 | 2, 3 |
| 1. Hook payload parser | 0 | 4, 10 | 2, 3 |
| 2. Memory schema engine | none | 5, 6, 10, 12 | 0, 1, 3 |
| 3. Runtime artifact boundary | none | 7, 8, 9, 11, 13 | 0, 1, 2 |
| 4. Full hook lifecycle commands | 1, 2 | 10, 12, 14 | 5, 6 |
| 5. Memory draft/update CLI | 2 | 10, 12, 14 | 4, 6 |
| 6. Tool lifecycle proposal model | 2 | 7, 10, 14 | 4, 5 |
| 7. Tool lifecycle CLI | 3, 6 | 10, 14 | 8, 9 |
| 8. Academy DB schema/init/query | 0, 3 | 9, 10, 11, 12 | 7 |
| 9. Context hydration v2 | 3, 7, 8 | 10, 14 | none |
| 10. Closeout enforcement v2 | 4, 5, 7, 9 | 12, 14 | 11 |
| 11. Academy DB migration/report/backup | 3, 8 | 12, 13, 14 | 10 |
| 12. Bootstrap delegation | 4, 10, 11 | 14 | 13 |
| 13. Doctor v2 | 3, 11 | 14 | 12 |
| 14. Final integration QA | 10, 12, 13 | final | none |

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: References + Acceptance Criteria + QA Scenarios.

- [ ] 0. Shared CLI IO And Command Split

  **What to do**: Split shared command concerns out of the central dispatcher before v2 features grow. Add small helpers for JSON output, exit-code mapping, profile-root option handling, stdin reading, and safe error envelopes. Keep `commands.py` as orchestration glue and move hook/memory/academy-specific behavior into dedicated handler modules as those tasks land.
  **Must NOT do**: Do not change user-visible command semantics. Do not rewrite unrelated commands. Do not introduce a framework or broad abstraction layer.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [1, 4, 5, 8, 12] | Blocked By: []

  **References**:
  - Pattern: `src/chat_lms_agent/commands.py` - current central dispatcher and JSON helpers.
  - Pattern: `src/chat_lms_agent/command_parser.py` - current argparse structure.
  - Pattern: `src/chat_lms_agent/doctor.py` - structured check/status output.
  - Constraint: `omo:programming` 250 pure LOC guidance for new Python modules.

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_cli_contracts.py::test_json_error_envelope_is_stable -q`.
  - [ ] RED first: `uv run pytest tests/test_cli_contracts.py::test_profile_root_option_rejects_public_repo_consistently -q`.
  - [ ] GREEN: existing `doctor`, `context hydrate`, `memory list`, `tool list`, and `side-panel validate` command contracts remain unchanged.
  - [ ] GREEN: new helpers make stdin and JSON behavior reusable by hook, memory, and academy DB tasks.

  **QA Scenarios**:
  ```
  Scenario: existing CLI contracts remain stable
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-0-cli-contracts -Command "uv run python -m chat_lms_agent doctor --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent context hydrate --for-codex --json }" -Evidence evidence/harness-v2/task-0-cli-contracts.txt
    Expected: exit_code: 0 and stdout remains valid JSON for both commands
    Evidence: evidence/harness-v2/task-0-cli-contracts.txt

  Scenario: profile-root rejection is shared
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-0-profile-root-reject -Command "uv run python -m chat_lms_agent context hydrate --profile-root . --for-codex --json" -Evidence evidence/harness-v2/task-0-profile-root-reject.txt
    Expected: stdout JSON reports PUBLIC_REPO_STATE_REJECTED without traceback
    Evidence: evidence/harness-v2/task-0-profile-root-reject.txt
  ```

  **Commit**: YES | Message: `refactor(cli): share json and profile helpers` | Files: [`src/chat_lms_agent/cli_io.py`, `src/chat_lms_agent/commands.py`, `tests/test_cli_contracts.py`]

- [ ] 1. Hook Payload Parser And Event Contract

  **What to do**: Add a pure hook payload parser module that reads stdin JSON for `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PostCompact`, and `Stop`. It must normalize absent/malformed payloads into typed results, extract changed files when present, and never traceback. Keep the current `--changed-files` flag as an override for local QA.
  **Must NOT do**: Do not register new hooks yet. Do not change closeout behavior yet. Do not parse payloads with ad-hoc string slicing.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [4, 10] | Blocked By: [0]

  **References**:
  - Pattern: `src/chat_lms_agent/command_parser.py` - hook subcommands already exist.
  - Pattern: `src/chat_lms_agent/commands.py` - current `_hook` function is the integration point.
  - Pattern: `tests/test_hooks.py` - existing subprocess hook tests.
  - API/Type: `src/chat_lms_agent/state.py` - reuse `JsonValue` style for JSON-shaped payloads.

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_hook_payloads.py::test_post_tool_use_payload_extracts_changed_files -q` fails before parser exists.
  - [ ] RED first: `uv run pytest tests/test_hook_payloads.py::test_malformed_hook_payload_returns_contract_error_without_traceback -q` fails before parser exists.
  - [ ] GREEN: parsed payloads expose `event_name`, `changed_files`, `session_id`, and `warnings`.
  - [ ] GREEN: malformed stdin exits with JSON `status: ERROR`, `error_code: INVALID_HOOK_PAYLOAD`, and no traceback.

  **QA Scenarios**:
  ```
  Scenario: parse PostToolUse changed files
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-1-hook-payload -Command "Get-Content tests/fixtures/hooks/post_tool_use_changed_files.json | uv run python -m chat_lms_agent hook post-tool-use --json" -Evidence evidence/harness-v2/task-1-hook-payload.txt
    Expected: exit_code: 0 or 5, stdout JSON mentions src/chat_lms_agent/agent_tools.py and never contains traceback
    Evidence: evidence/harness-v2/task-1-hook-payload.txt

  Scenario: malformed hook payload is safe
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-1-hook-payload-bad -Command "'{bad json' | uv run python -m chat_lms_agent hook post-tool-use --json" -Evidence evidence/harness-v2/task-1-hook-payload-bad.txt
    Expected: exit_code: 2 and stdout JSON has error_code INVALID_HOOK_PAYLOAD
    Evidence: evidence/harness-v2/task-1-hook-payload-bad.txt
  ```

  **Commit**: YES | Message: `feat(hooks): parse lifecycle payloads` | Files: [`src/chat_lms_agent/hook_payloads.py`, `src/chat_lms_agent/commands.py`, `tests/test_hook_payloads.py`, `tests/fixtures/hooks/*.json`]

- [ ] 2. Memory Schema And Obligation Engine

  **What to do**: Add a memory obligation engine that defines durable memory kinds: `tool:<id>`, `db:<id>`, `schema:<id>`, `query:<id>`, `panel:<view>`, and `decision:<topic>`. It must compute obligations from changed files, tool proposals, DB operations, and side-panel changes. It must return draftable obligations, not write them automatically.
  **Must NOT do**: Do not silently persist memory from hooks. Do not weaken existing `session closeout --verify-memory` active-tool checks.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [5, 6, 10, 12] | Blocked By: []

  **References**:
  - Pattern: `src/chat_lms_agent/agent_tools.py` - current registry memory obligation text and managed paths.
  - Pattern: `src/chat_lms_agent/commands.py` - `_write_closeout` currently checks `tool:<name>`.
  - Pattern: `src/chat_lms_agent/state.py` - current memory payload shape.
  - Test: `tests/test_harness_contracts.py::test_closeout_blocks_when_active_tool_has_no_memory`.

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_memory_obligations.py::test_registry_path_change_requires_tool_memory_draft -q`.
  - [ ] RED first: `uv run pytest tests/test_memory_obligations.py::test_db_schema_change_requires_schema_and_decision_memory -q`.
  - [ ] GREEN: obligation output is sorted, deterministic, and uses fixed memory keys.
  - [ ] GREEN: existing active-tool closeout behavior is preserved.

  **QA Scenarios**:
  ```
  Scenario: registry change produces draftable obligation
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-2-memory-obligation -Command "uv run python -m chat_lms_agent memory verify --changed-files src/chat_lms_agent/agent_tools.py --json" -Evidence evidence/harness-v2/task-2-memory-obligation.txt
    Expected: exit_code: 5 and stdout JSON includes MEMORY_UPDATE_REQUIRED and draftable key tool:agent-tools
    Evidence: evidence/harness-v2/task-2-memory-obligation.txt

  Scenario: active tool memory still closes out
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-2-closeout-regression -Command "uv run python -m chat_lms_agent session closeout --verify-memory --profile test-fixture --json" -Evidence evidence/harness-v2/task-2-closeout-regression.txt
    Expected: exit_code: 0 and stdout JSON has status PASS
    Evidence: evidence/harness-v2/task-2-closeout-regression.txt
  ```

  **Commit**: YES | Message: `feat(memory): compute harness obligations` | Files: [`src/chat_lms_agent/memory_obligations.py`, `src/chat_lms_agent/commands.py`, `tests/test_memory_obligations.py`]

- [ ] 3. Runtime Artifact Boundary For V2

  **What to do**: Extend privacy/boundary contracts for DB files, imports, reports, backups, logs, generated memory, and evidence. Add helper functions that resolve private profile artifact roots and reject public repo roots. Update `.gitignore` and tests only if a missing ignored pattern is found.
  **Must NOT do**: Do not create real DB files in the public repo. Do not inspect private profile data.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [7, 8, 9, 11, 13] | Blocked By: []

  **References**:
  - Boundary: `AGENTS.md`
  - Boundary: `docs/runtime-boundary.md`
  - Pattern: `src/chat_lms_agent/state.py::resolve_profile_state`
  - Test: `tests/test_repo_privacy.py`
  - Script: `scripts/bootstrap.ps1` private profile path generation.

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_runtime_artifacts.py::test_public_repo_rejects_academy_db_root -q`.
  - [ ] RED first: `uv run pytest tests/test_repo_privacy.py::test_v2_runtime_artifacts_are_ignored_or_outside_repo -q`.
  - [ ] GREEN: all runtime roots resolve under explicit temp/private profile roots.
  - [ ] GREEN: public repo privacy scan still passes.

  **QA Scenarios**:
  ```
  Scenario: public repo DB root is rejected
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-3-boundary-reject -Command "uv run python -m chat_lms_agent academy-db init --profile-root . --json" -Evidence evidence/harness-v2/task-3-boundary-reject.txt
    Expected: exit_code: 4 and stdout JSON has error_code PUBLIC_REPO_STATE_REJECTED
    Evidence: evidence/harness-v2/task-3-boundary-reject.txt

  Scenario: temp runtime root is accepted
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-3-boundary-temp -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-boundary'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent profile inspect --profile-root $root --json" -Evidence evidence/harness-v2/task-3-boundary-temp.txt
    Expected: exit_code: 0 and stdout JSON redacts concrete private paths
    Evidence: evidence/harness-v2/task-3-boundary-temp.txt
  ```

  **Commit**: YES | Message: `test(privacy): guard v2 runtime artifacts` | Files: [`src/chat_lms_agent/runtime_paths.py`, `tests/test_runtime_artifacts.py`, `tests/test_repo_privacy.py`, `.gitignore`]

- [ ] 4. Register Full Hook Lifecycle

  **What to do**: Update `hooks/hooks.json` and CLI behavior so all five lifecycle events are registered and executable: `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PostCompact`, `Stop`. Each registered command must be covered by a test that reads `hooks/hooks.json`, runs the command with fixture stdin, and asserts JSON/exit-code contracts.
  **Must NOT do**: Do not leave lifecycle commands implemented but unregistered. Do not add hook entries that call missing commands.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [10, 12, 14] | Blocked By: [1, 2]

  **References**:
  - Current registration: `hooks/hooks.json`
  - Parser: `src/chat_lms_agent/command_parser.py`
  - Handler: `src/chat_lms_agent/commands.py::_hook`
  - Test: `tests/test_hooks.py::test_hook_commands_from_hooks_json_execute`

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_hooks.py::test_hooks_json_registers_full_lifecycle -q`.
  - [ ] RED first: `uv run pytest tests/test_hooks.py::test_every_lifecycle_hook_executes_with_fixture_payload -q`.
  - [ ] GREEN: `hooks/hooks.json` contains all five events.
  - [ ] GREEN: malformed payload fixtures never traceback.

  **QA Scenarios**:
  ```
  Scenario: SessionStart injects v2 context
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-4-hook-session-start -Command "Get-Content tests/fixtures/hooks/session_start.json | uv run python -m chat_lms_agent hook session-start --json" -Evidence evidence/harness-v2/task-4-hook-session-start.txt
    Expected: exit_code: 0 and stdout JSON has hookSpecificOutput.additionalContext containing agent_tools and memory_policy
    Evidence: evidence/harness-v2/task-4-hook-session-start.txt

  Scenario: PostCompact blocks unresolved memory draft
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-4-hook-post-compact -Command "Get-Content tests/fixtures/hooks/post_compact_unresolved_memory.json | uv run python -m chat_lms_agent hook post-compact --json" -Evidence evidence/harness-v2/task-4-hook-post-compact.txt
    Expected: exit_code: 5 and stdout JSON includes MEMORY_UPDATE_REQUIRED
    Evidence: evidence/harness-v2/task-4-hook-post-compact.txt
  ```

  **Commit**: YES | Message: `feat(hooks): register full lifecycle` | Files: [`hooks/hooks.json`, `src/chat_lms_agent/commands.py`, `tests/test_hooks.py`, `tests/fixtures/hooks/*.json`]

- [ ] 5. Memory Draft Update Apply CLI

  **What to do**: Add `memory draft`, `memory verify`, and `memory apply-draft`. `draft` creates reviewable JSON from obligations, `verify` blocks when required memory is missing, and `apply-draft` persists only an explicit draft file. Keep `memory upsert/list` backward compatible.
  **Must NOT do**: Do not auto-write from hooks. Do not store raw hook payloads or prompts as memory.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [10, 12, 14] | Blocked By: [2]

  **References**:
  - Parser: `src/chat_lms_agent/command_parser.py::_add_memory_parser`
  - Handler: `src/chat_lms_agent/commands.py::_memory`
  - State: `src/chat_lms_agent/state.py::save_memory`
  - QA skill: `chat-lms-qa` requires tests plus real transcript.

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_memory_drafts.py::test_memory_draft_for_tool_change_is_reviewable -q`.
  - [ ] RED first: `uv run pytest tests/test_memory_drafts.py::test_apply_draft_replaces_existing_memory_key -q`.
  - [ ] GREEN: `memory draft` writes no state.
  - [ ] GREEN: `memory apply-draft` redacts private-like values before storage or rejects unsafe drafts.

  **QA Scenarios**:
  ```
  Scenario: draft then apply memory
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-5-memory-draft-apply -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-memory'; $draft=Join-Path $root 'draft.json'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; New-Item -ItemType Directory -Force $root | Out-Null; uv run python -m chat_lms_agent memory draft --profile-root $root --for tool-change --changed-files src/chat_lms_agent/agent_tools.py --out $draft --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory apply-draft --profile-root $root --from $draft --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory list --profile-root $root --json }" -Evidence evidence/harness-v2/task-5-memory-draft-apply.txt
    Expected: final stdout has tool:agent-tools memory and no private path leak
    Evidence: evidence/harness-v2/task-5-memory-draft-apply.txt

  Scenario: unsafe memory draft is rejected
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-5-memory-draft-unsafe -Command "uv run python -m chat_lms_agent memory apply-draft --from tests/fixtures/memory/unsafe-draft.json --json" -Evidence evidence/harness-v2/task-5-memory-draft-unsafe.txt
    Expected: exit_code: 4 and stdout JSON has error_code UNSAFE_MEMORY_DRAFT
    Evidence: evidence/harness-v2/task-5-memory-draft-unsafe.txt
  ```

  **Commit**: YES | Message: `feat(memory): draft and apply durable updates` | Files: [`src/chat_lms_agent/memory_drafts.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `tests/test_memory_drafts.py`, `tests/fixtures/memory/*.json`]

- [ ] 6. Tool Lifecycle Proposal Model

  **What to do**: Extend agent-tool contracts with `safety_boundary`, `test_contract`, `activation_policy`, `version`, and `lifecycle_status`. Validate backward-compatible v1 proposals while requiring new fields for scaffold/register/promote flows.
  **Must NOT do**: Do not activate tools in this task. Do not break existing `agent-tools validate` C001/C002 behavior.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [7, 10, 14] | Blocked By: [2]

  **References**:
  - Registry: `src/chat_lms_agent/agent_tools.py`
  - Handler: `src/chat_lms_agent/agent_tool_handlers.py`
  - Test: `tests/test_tool_registry.py`
  - Doc: `docs/agent-tool-registry.md`

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_agent_tool_lifecycle_model.py::test_v2_tool_contract_requires_safety_and_test_contract -q`.
  - [ ] RED first: `uv run pytest tests/test_agent_tool_lifecycle_model.py::test_v1_validate_behavior_remains_compatible -q`.
  - [ ] GREEN: model validation reports all missing v2 fields together.
  - [ ] GREEN: docs describe v2 lifecycle fields.

  **QA Scenarios**:
  ```
  Scenario: v2 proposal validates
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-6-tool-model-valid -Command "uv run python -m chat_lms_agent agent-tools validate --from tests/fixtures/agent_tools/v2-valid-tool.json --json" -Evidence evidence/harness-v2/task-6-tool-model-valid.txt
    Expected: exit_code: 0 and stdout JSON status PASS
    Evidence: evidence/harness-v2/task-6-tool-model-valid.txt

  Scenario: v2 proposal reports all missing lifecycle fields
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-6-tool-model-invalid -Command "uv run python -m chat_lms_agent agent-tools validate --from tests/fixtures/agent_tools/v2-missing-lifecycle.json --json" -Evidence evidence/harness-v2/task-6-tool-model-invalid.txt
    Expected: exit_code: 2 and stdout includes MISSING_SAFETY_BOUNDARY and MISSING_TEST_CONTRACT
    Evidence: evidence/harness-v2/task-6-tool-model-invalid.txt
  ```

  **Commit**: YES | Message: `feat(agent-tools): validate lifecycle contracts` | Files: [`src/chat_lms_agent/agent_tools.py`, `docs/agent-tool-registry.md`, `tests/test_agent_tool_lifecycle_model.py`, `tests/fixtures/agent_tools/*.json`]

- [ ] 7. Agent Tools Lifecycle CLI

  **What to do**: Add `agent-tools scaffold`, `agent-tools register`, `agent-tools promote`, `agent-tools deprecate`, `agent-tools explain`, and `agent-tools doctor`. Store lifecycle records in private profile state. `promote` may activate data-driven commands only when validation, tests, and memory obligations pass. Module commands remain `review_required` until a later implementation plan/test exists.
  **Must NOT do**: Do not create executable source code in scaffold. Do not deprecate or mutate built-in default registry entries unless a profile overlay is supplied.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [10, 14] | Blocked By: [3, 6]

  **References**:
  - Parser: `src/chat_lms_agent/command_parser.py::_add_agent_tools_parser`
  - Existing per-profile tool lifecycle: `src/chat_lms_agent/tool_handlers.py`
  - State: `src/chat_lms_agent/state.py`
  - Tests: `tests/test_tool_registry.py`

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_agent_tools_lifecycle_cli.py::test_scaffold_register_promote_round_trip -q`.
  - [ ] RED first: `uv run pytest tests/test_agent_tools_lifecycle_cli.py::test_module_command_promote_requires_review -q`.
  - [ ] GREEN: promoted tools appear in `agent-tools list --profile-root <temp> --json`.
  - [ ] GREEN: `agent-tools explain <id>` returns command contract and memory obligation.

  **QA Scenarios**:
  ```
  Scenario: scaffold register promote safe workflow
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-7-agent-tools-lifecycle -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-tools'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent agent-tools scaffold --profile-root $root --from tests/fixtures/agent_tools/v2-valid-tool.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent agent-tools register --profile-root $root --id attendance-risk --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent agent-tools promote --profile-root $root --id attendance-risk --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent agent-tools list --profile-root $root --json }" -Evidence evidence/harness-v2/task-7-agent-tools-lifecycle.txt
    Expected: final stdout includes attendance-risk with lifecycle_status active
    Evidence: evidence/harness-v2/task-7-agent-tools-lifecycle.txt

  Scenario: module command stays review required
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-7-agent-tools-module-review -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-tools-module'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent agent-tools scaffold --profile-root $root --from tests/fixtures/agent_tools/v2-module-tool.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent agent-tools promote --profile-root $root --id module-report-builder --json }" -Evidence evidence/harness-v2/task-7-agent-tools-module-review.txt
    Expected: exit_code: 3 and stdout JSON has status NEEDS_REVIEW
    Evidence: evidence/harness-v2/task-7-agent-tools-module-review.txt
  ```

  **Commit**: YES | Message: `feat(agent-tools): manage lifecycle overlays` | Files: [`src/chat_lms_agent/agent_tool_lifecycle.py`, `src/chat_lms_agent/agent_tool_handlers.py`, `src/chat_lms_agent/command_parser.py`, `tests/test_agent_tools_lifecycle_cli.py`]

- [ ] 8. Academy DB Spec Init Query Foundation

  **What to do**: Add an `academy-db` namespace with `spec`, `init`, `inspect`, `schema show`, `query list`, and `query run`. The first schema is synthetic/public-safe and private-profile-scoped. `init` creates runtime artifacts only under an explicit safe profile root.
  **Must NOT do**: Do not import real learner data. Do not write DB artifacts in the public repo. Do not add external service adapters.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [9, 10, 11, 12] | Blocked By: [0, 3]

  **References**:
  - Planned registry entry: `src/chat_lms_agent/agent_tools.py` tool id `academy-db`.
  - Boundary: `docs/runtime-boundary.md`
  - Privacy: `tests/test_repo_privacy.py`
  - Bootstrap private data roots: `scripts/bootstrap.ps1`

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_academy_db_cli.py::test_academy_db_spec_exposes_schema_and_commands -q`.
  - [ ] RED first: `uv run pytest tests/test_academy_db_cli.py::test_init_rejects_public_repo_profile_root -q`.
  - [ ] RED first: `uv run pytest tests/test_academy_db_cli.py::test_query_run_uses_synthetic_fixture_data -q`.
  - [ ] GREEN: `academy-db` status in `agent-tools list` moves from `planned` to `active` with real command contracts.

  **QA Scenarios**:
  ```
  Scenario: initialize academy DB in temp profile
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-8-academy-db-init -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-db'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent academy-db inspect --profile-root $root --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent academy-db query list --profile-root $root --json }" -Evidence evidence/harness-v2/task-8-academy-db-init.txt
    Expected: exit_code: 0 and stdout includes schema_version and public_safe true
    Evidence: evidence/harness-v2/task-8-academy-db-init.txt

  Scenario: public repo DB init is blocked
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-8-academy-db-public-block -Command "uv run python -m chat_lms_agent academy-db init --profile-root . --json" -Evidence evidence/harness-v2/task-8-academy-db-public-block.txt
    Expected: exit_code: 4 and stdout JSON has error_code PUBLIC_REPO_STATE_REJECTED
    Evidence: evidence/harness-v2/task-8-academy-db-public-block.txt
  ```

  **Commit**: YES | Message: `feat(academy-db): add private schema and query foundation` | Files: [`src/chat_lms_agent/academy_db.py`, `src/chat_lms_agent/academy_db_handlers.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `tests/test_academy_db_cli.py`, `tests/fixtures/academy_db/*.json`]

- [ ] 9. Context Hydration V2

  **What to do**: Expand `context hydrate` to include v2 summaries: `hook_lifecycle`, `memory_obligations`, `tool_lifecycle`, `academy_db`, and existing `side_panel`. Include only concise command hints and public-safe status, not raw DB contents or full private paths.
  **Must NOT do**: Do not dump full DB records, full memory text, private roots, logs, reports, or backups.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [10, 14] | Blocked By: [3, 7, 8]

  **References**:
  - Current context: `src/chat_lms_agent/context.py`
  - Registry context helpers: `src/chat_lms_agent/agent_tools.py`
  - Side-panel contract: `src/chat_lms_agent/side_panel.py`
  - Tests: `tests/test_context_hydration.py`, `tests/test_tool_registry.py`

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_context_hydration_v2.py::test_hydrate_includes_hook_memory_tool_and_academy_inventory -q`.
  - [ ] RED first: `uv run pytest tests/test_context_hydration_v2.py::test_hydrate_does_not_leak_private_runtime_paths -q`.
  - [ ] GREEN: existing `side_panel`, `agent_tools`, `tool_registry`, and `memory_policy` keys remain.
  - [ ] GREEN: hydration remains deterministic under empty profile state.

  **QA Scenarios**:
  ```
  Scenario: hydrate v2 operating context
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-9-context-v2 -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-context'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent context hydrate --profile-root $root --for-codex --json }" -Evidence evidence/harness-v2/task-9-context-v2.txt
    Expected: stdout JSON includes hook_lifecycle, memory_obligations, tool_lifecycle, academy_db, side_panel
    Evidence: evidence/harness-v2/task-9-context-v2.txt

  Scenario: unsafe profile root hydration stays blocked
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-9-context-public-block -Command "uv run python -m chat_lms_agent context hydrate --profile-root . --for-codex --json" -Evidence evidence/harness-v2/task-9-context-public-block.txt
    Expected: status UNSAFE and warning PUBLIC_REPO_STATE_REJECTED
    Evidence: evidence/harness-v2/task-9-context-public-block.txt
  ```

  **Commit**: YES | Message: `feat(context): hydrate v2 harness inventory` | Files: [`src/chat_lms_agent/context.py`, `tests/test_context_hydration_v2.py`]

- [ ] 10. Closeout Enforcement V2

  **What to do**: Replace narrow closeout checks with a shared verifier that blocks unresolved memory drafts, broken hooks, unpromoted tool lifecycle changes, academy DB schema/query changes without decision records, and side-panel contract changes without memory. Stop and PostCompact hooks must call this verifier.
  **Must NOT do**: Do not silently pass unknown obligations. Do not write vague memory on the user's behalf.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: [12, 14] | Blocked By: [4, 5, 7, 9]

  **References**:
  - Current closeout: `src/chat_lms_agent/commands.py::_write_closeout`
  - Hook guard: `src/chat_lms_agent/agent_tools.py::touches_agent_tool_registry`
  - Tests: `tests/test_harness_contracts.py::test_closeout_blocks_when_active_tool_has_no_memory`

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_session_closeout_v2.py::test_closeout_blocks_unresolved_memory_draft -q`.
  - [ ] RED first: `uv run pytest tests/test_session_closeout_v2.py::test_closeout_blocks_academy_db_schema_change_without_decision -q`.
  - [ ] RED first: `uv run pytest tests/test_hooks.py::test_post_compact_uses_closeout_verifier -q`.
  - [ ] GREEN: existing closeout active-tool memory behavior remains.

  **QA Scenarios**:
  ```
  Scenario: closeout blocks unresolved DB obligation
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-10-closeout-db-block -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-closeout'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent session closeout --profile-root $root --verify-memory --json }" -Evidence evidence/harness-v2/task-10-closeout-db-block.txt
    Expected: exit_code: 5 and stdout JSON lists schema or db memory obligation
    Evidence: evidence/harness-v2/task-10-closeout-db-block.txt

  Scenario: closeout passes after memory draft is applied
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-10-closeout-pass -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-closeout-pass'; $draft=Join-Path $root 'db-memory.json'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory draft --profile-root $root --for academy-db-init --out $draft --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory apply-draft --profile-root $root --from $draft --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent session closeout --profile-root $root --verify-memory --json }" -Evidence evidence/harness-v2/task-10-closeout-pass.txt
    Expected: exit_code: 0 and stdout JSON status PASS
    Evidence: evidence/harness-v2/task-10-closeout-pass.txt
  ```

  **Commit**: YES | Message: `feat(session): enforce v2 closeout obligations` | Files: [`src/chat_lms_agent/session_closeout.py`, `src/chat_lms_agent/commands.py`, `tests/test_session_closeout_v2.py`, `tests/test_hooks.py`]

- [ ] 11. Academy DB Migration Import Report Backup Restore

  **What to do**: Extend `academy-db` with `migrate plan/apply`, `import plan/apply`, `report build`, `backup create`, `restore plan/apply`, and `doctor`. Risky writes require an existing backup or explicit `--dry-run`/plan step. Reports are generated only under private runtime report roots.
  **Must NOT do**: Do not connect to external systems. Do not write reports into public repo. Do not apply import/migration without a plan id.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: [12, 13, 14] | Blocked By: [3, 8]

  **References**:
  - Bootstrap backup behavior: `scripts/bootstrap.ps1`
  - Boundary: `docs/runtime-boundary.md`
  - Privacy test: `tests/test_repo_privacy.py`
  - Academy foundation from Task 8.

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_academy_db_migrations.py::test_migration_apply_requires_backup -q`.
  - [ ] RED first: `uv run pytest tests/test_academy_db_reports.py::test_report_build_writes_only_private_report_root -q`.
  - [ ] RED first: `uv run pytest tests/test_academy_db_restore.py::test_restore_apply_requires_plan_id -q`.
  - [ ] GREEN: all DB write commands are dry-run or private-root-only.

  **QA Scenarios**:
  ```
  Scenario: migration requires backup
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-11-db-migration-backup -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-migrate'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent academy-db migrate plan --profile-root $root --to next --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent academy-db migrate apply --profile-root $root --to next --json }" -Evidence evidence/harness-v2/task-11-db-migration-backup.txt
    Expected: final command exits nonzero and stdout JSON has error_code BACKUP_REQUIRED
    Evidence: evidence/harness-v2/task-11-db-migration-backup.txt

  Scenario: report builds in private report root
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-11-db-report-private -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-report'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent academy-db report build --profile-root $root --report class-overview --json }" -Evidence evidence/harness-v2/task-11-db-report-private.txt
    Expected: exit_code: 0 and stdout JSON report path is under temp profile root, not public repo
    Evidence: evidence/harness-v2/task-11-db-report-private.txt
  ```

  **Commit**: YES | Message: `feat(academy-db): add migration report backup workflows` | Files: [`src/chat_lms_agent/academy_db_maintenance.py`, `src/chat_lms_agent/academy_db_handlers.py`, `tests/test_academy_db_migrations.py`, `tests/test_academy_db_reports.py`, `tests/test_academy_db_restore.py`]

- [ ] 12. Bootstrap Delegation To Python CLI

  **What to do**: Reduce `scripts/bootstrap.ps1` to argument parsing plus calls into Python CLI commands: `bootstrap plan`, `bootstrap apply`, and `bootstrap sync-runtime`. Generated private hooks must call the new full hook lifecycle commands. Tests must use temp `APPDATA` and `LOCALAPPDATA`.
  **Must NOT do**: Do not write real user profile directories in tests. Do not embed new context rendering logic in PowerShell.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: [14] | Blocked By: [4, 10, 11]

  **References**:
  - Script: `scripts/bootstrap.ps1`
  - Tests: `tests/test_bootstrap.py`
  - Runtime boundary: `docs/runtime-boundary.md`
  - Hook registration from Task 4.

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_bootstrap_v2.py::test_bootstrap_dry_run_lists_python_cli_delegation -q`.
  - [ ] RED first: `uv run pytest tests/test_bootstrap_v2.py::test_user_mode_generates_full_lifecycle_hooks_in_temp_env -q`.
  - [ ] GREEN: PowerShell no longer owns large SessionStart context rendering.
  - [ ] GREEN: existing bootstrap dry-run tests remain green.

  **QA Scenarios**:
  ```
  Scenario: bootstrap dry-run delegates
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-12-bootstrap-dry-run -Command "powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -DryRun -Mode User -Profile qa-demo" -Evidence evidence/harness-v2/task-12-bootstrap-dry-run.txt
    Expected: exit_code: 0 and transcript lists bootstrap plan/apply/sync-runtime Python CLI delegation
    Evidence: evidence/harness-v2/task-12-bootstrap-dry-run.txt

  Scenario: bootstrap temp profile full hooks
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-12-bootstrap-temp-profile -Command "$env:LOCALAPPDATA=Join-Path $env:TEMP 'chat-lms-harness-v2-local'; $env:APPDATA=Join-Path $env:TEMP 'chat-lms-harness-v2-roaming'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $env:LOCALAPPDATA,$env:APPDATA; powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -Mode User -Profile qa-demo -NonInteractive" -Evidence evidence/harness-v2/task-12-bootstrap-temp-profile.txt
    Expected: exit_code: 0 and generated hook config contains SessionStart, UserPromptSubmit, PostToolUse, PostCompact, Stop
    Evidence: evidence/harness-v2/task-12-bootstrap-temp-profile.txt
  ```

  **Commit**: YES | Message: `refactor(bootstrap): delegate runtime wiring to cli` | Files: [`scripts/bootstrap.ps1`, `src/chat_lms_agent/bootstrap_handlers.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `tests/test_bootstrap_v2.py`]

- [ ] 13. Doctor V2 Executable Harness Health

  **What to do**: Expand doctor checks to execute real harness checks: hook registration/executability, memory obligation engine, agent-tool lifecycle state, academy DB schema/query/backup status, runtime artifact boundary, and side-panel contract regression. `--repair` may only perform safe local repairs and must report approval-required actions without doing them.
  **Must NOT do**: Do not mark planned commands healthy. Do not create DB files in public repo. Do not leak private paths.

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: [14] | Blocked By: [3, 11]

  **References**:
  - Current doctor: `src/chat_lms_agent/doctor.py`
  - Doctor command wrapper: `src/chat_lms_agent/commands.py::_doctor`
  - QA skill: `chat-lms-qa`
  - Tests: `tests/test_doctor.py`

  **Acceptance Criteria**:
  - [ ] RED first: `uv run pytest tests/test_doctor_v2.py::test_doctor_fails_when_registered_hook_command_missing -q`.
  - [ ] RED first: `uv run pytest tests/test_doctor_v2.py::test_doctor_reports_unresolved_memory_obligation -q`.
  - [ ] RED first: `uv run pytest tests/test_doctor_v2.py::test_doctor_reports_academy_db_private_boundary -q`.
  - [ ] GREEN: `doctor --repair --json` never performs migrations/imports/restores.

  **QA Scenarios**:
  ```
  Scenario: doctor passes healthy temp profile
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-13-doctor-v2-pass -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-doctor'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent doctor --profile-root $root --repair --json }" -Evidence evidence/harness-v2/task-13-doctor-v2-pass.txt
    Expected: exit_code: 0 and checks include hooks, memory_obligations, agent_tools, academy_db, runtime_boundary
    Evidence: evidence/harness-v2/task-13-doctor-v2-pass.txt

  Scenario: doctor detects broken hook fixture
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-13-doctor-v2-broken-hook -Command "uv run python -m chat_lms_agent doctor --profile broken-hook-fixture --json" -Evidence evidence/harness-v2/task-13-doctor-v2-broken-hook.txt
    Expected: nonzero exit and stdout JSON has a hook_executable failure
    Evidence: evidence/harness-v2/task-13-doctor-v2-broken-hook.txt
  ```

  **Commit**: YES | Message: `feat(doctor): verify v2 harness health` | Files: [`src/chat_lms_agent/doctor.py`, `src/chat_lms_agent/doctor_checks.py`, `tests/test_doctor_v2.py`, `tests/fixtures/profiles/*`]

- [ ] 14. Final Integration And Regression Gate

  **What to do**: Run the complete v2 story end-to-end in a temp profile: bootstrap, hook session-start, scaffold/promote a safe tool, initialize academy DB, run query, build report, draft/apply memory, hydrate context, closeout, doctor, and privacy scan. Fix only issues found by the gate; do not add new features.
  **Must NOT do**: Do not skip failing checks. Do not produce real private artifacts in public repo.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: [final] | Blocked By: [10, 12, 13]

  **References**:
  - All prior task evidence.
  - Final gates in this plan.
  - Existing `tests/test_package_import.py`, `tests/test_repo_privacy.py`, `tests/test_harness_contracts.py`.

  **Acceptance Criteria**:
  - [ ] GREEN: `uv run pytest -q` exits 0.
  - [ ] GREEN: `uv run ruff check src tests` exits 0.
  - [ ] GREEN: `uv run basedpyright src` exits 0.
  - [ ] GREEN: all evidence files for tasks 1-13 exist and name cleanup receipts.
  - [ ] GREEN: independent QA agent reruns the final story and reports no blockers.

  **QA Scenarios**:
  ```
  Scenario: full v2 harness happy path
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-14-full-v2-happy -Command "$root=Join-Path $env:TEMP 'chat-lms-harness-v2-final'; $draft=Join-Path $root 'memory.json'; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent academy-db init --profile-root $root --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent agent-tools scaffold --profile-root $root --from tests/fixtures/agent_tools/v2-valid-tool.json --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory draft --profile-root $root --for academy-db-init --out $draft --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory apply-draft --profile-root $root --from $draft --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent context hydrate --profile-root $root --for-codex --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent session closeout --profile-root $root --verify-memory --json }" -Evidence evidence/harness-v2/task-14-full-v2-happy.txt
    Expected: final exit_code: 0 and transcript contains academy_db, agent_tools, memory, closeout PASS
    Evidence: evidence/harness-v2/task-14-full-v2-happy.txt

  Scenario: public repo remains publishable
    Tool: PowerShell CLI capture
    Steps: powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-14-privacy-final -Command "uv run pytest tests/test_repo_privacy.py -q" -Evidence evidence/harness-v2/task-14-privacy-final.txt
    Expected: exit_code: 0 and no forbidden runtime artifacts reported
    Evidence: evidence/harness-v2/task-14-privacy-final.txt
  ```

  **Commit**: YES | Message: `test(harness): verify v2 end-to-end flow` | Files: [`tests/test_harness_v2_integration.py`, `tests/test_repo_privacy.py`, `plans/harness-v2-agentic-hardening-plan.md`]

## Final Verification Wave
> ALL must APPROVE. Present consolidated results to the user before execution is called complete.
- [ ] F1. Plan Compliance Audit
  - Command: `uv run pytest tests/test_harness_v2_integration.py -q`
  - Evidence: `evidence/harness-v2/f1-plan-compliance.txt`
  - Pass condition: every v2 capability named in this plan has a green executable test or an explicit deferred note approved before implementation starts.
- [ ] F2. Static Quality Gate
  - Command: `uv run ruff check src tests` and `uv run basedpyright src`
  - Evidence: `evidence/harness-v2/f2-static-quality.txt`
  - Pass condition: zero lint/type errors in touched Python modules.
- [ ] F3. Full Hook Reality Gate
  - Command: run every command registered in `hooks/hooks.json` with fixture stdin through `scripts/qa/capture-command.ps1`.
  - Evidence: `evidence/harness-v2/f3-hooks.txt`
  - Pass condition: all five lifecycle hooks execute, malformed stdin is handled, and no hook entry points to a missing command.
- [ ] F4. Memory/Tool Lifecycle Reality Gate
  - Command: scaffold a safe tool proposal, validate it, promote it, generate required memory draft, apply the draft, hydrate context, then close out.
  - Evidence: `evidence/harness-v2/f4-memory-tools.txt`
  - Pass condition: no tool lifecycle change can close out without the required memory/decision record.
- [ ] F5. Academy DB Private Runtime Gate
  - Command: initialize a temp profile, run named queries, build one report, create backup, plan restore, and attempt a public-repo root write.
  - Evidence: `evidence/harness-v2/f5-academy-db.txt`
  - Pass condition: temp/private profile succeeds, public repo root is rejected, and reported paths are redacted or relative.
- [ ] F6. Public Repo Privacy Gate
  - Command: `uv run pytest tests/test_repo_privacy.py -q` plus `git status --short`
  - Evidence: `evidence/harness-v2/f6-privacy.txt`
  - Pass condition: no generated DB/report/log/backup/runtime-memory artifacts are tracked or left unignored.
- [ ] F7. Independent QA Agent Review
  - Command: QA/testing agent reruns F1-F6 from a clean temp profile and reviews diff against this plan.
  - Evidence: `evidence/harness-v2/f7-independent-qa.md`
  - Pass condition: QA reports APPROVE with no blocker findings.

## Commit Strategy
- One logical commit per task, after task tests and QA evidence pass.
- Use Conventional Commits.
- Final commit footer: `Plan: plans/harness-v2-agentic-hardening-plan.md`.

## Success Criteria
- New Codex sessions automatically receive tool, memory, DB, and side-panel operating context.
- Agent can create, validate, register, promote, explain, and deprecate reusable tools without ad-hoc from-scratch work.
- Tool/DB/side-panel changes cannot close out without durable memory or decision records.
- Academy DB operations are CLI-first, private-profile-scoped, backed up before risky writes, and privacy-safe in public tests.
- Doctor detects broken hooks, broken tool contracts, unresolved memory obligations, unsafe runtime roots, and academy DB integrity failures.
