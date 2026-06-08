# Chat LMS Agent Harness V1 Implementation Wave Plan

## TL;DR
> Summary:      Implement the self-maintaining harness v1 by replacing the hand-matched CLI with typed command modules, private profile state, durable tool/memory registries, context hydration, hook closeout, doctor checks, and bootstrap delegation.
> Deliverables:
> - Public-safe QA capture wrapper, fixtures, and privacy coverage.
> - `chat-lms`/`python -m chat_lms_agent` command tree for `doctor`, `context`, `profile`, `tool`, `memory`, `hook`, `session`, `bootstrap`, and existing `onboarding`.
> - Temp/private profile state store with atomic writes, redaction, tool registry, memory/decision records, hook execution, closeout, doctor checks, and bootstrap delegation.
> - Agent-executed evidence for happy CLI lifecycle, adversarial CLI/boundary/closeout, and hook/test regression.
> Effort:       Large
> Risk:         High - the change crosses CLI parsing, state persistence, hooks, bootstrap, privacy boundaries, and strict test/type/lint gates.

## Scope
### Must have
- Tests before implementation for every task; each task captures RED and GREEN evidence.
- Preserve package entrypoints: `pyproject.toml:16-17` exposes `chat-lms = "chat_lms_agent.cli:app"` and `src/chat_lms_agent/__main__.py:1-5` forwards module execution to `main`.
- Replace current string matching in `src/chat_lms_agent/cli.py:26-42` with stdlib `argparse` command routing and deterministic JSON errors.
- Implement profile-aware state outside the public repo or under per-test temp directories only, honoring `AGENTS.md:7-20` and `docs/runtime-boundary.md:18-31`.
- Implement deterministic exit codes: `0` success, `2` validation/contract error, `3` approval required, `4` unsafe/privacy boundary violation, `5` closeout blocked.
- Implement tool lifecycle: draft, validate, activate, list, show, deprecate. Delete remains out of scope.
- Implement memory lifecycle: upsert, list, compact, archive, plus decision records needed for self-maintenance and closeout.
- Implement context hydration that includes active tool inventory and scoped memory, replacing the static placeholder in `src/chat_lms_agent/context.py:9-17`.
- Implement hook commands for SessionStart, UserPromptSubmit, PostToolUse, PostCompact, and Stop, and ensure every command in `hooks/hooks.json:1-10` is executable.
- Implement `session closeout --verify-memory --json` so missing durable memory/decision obligations return exit code `5`.
- Expand doctor from path checks in `src/chat_lms_agent/doctor.py:29-73` to executable harness checks.
- Refactor `scripts/bootstrap.ps1` so PowerShell is a thin launcher; profile generation and hook rendering are delegated to Python CLI commands.
- Keep edited Python files under 250 pure LOC where practical by splitting helpers into focused modules.
- Final verification must include `uv run pytest -q`, `uv run ruff check .`, `uv run basedpyright`, and real CLI transcript evidence.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- No real learner records, private reports, saved credentials, generated local DBs, local memory, or machine-specific paths in tracked files.
- No real external writes or destructive local changes without explicit user confirmation.
- No arbitrary Python code generation and automatic activation in v1; generated executable tools remain drafts until reviewed with tests.
- No natural-language command parser, daemon, model router, chat platform, or broad tool zoo.
- No PowerShell script that embeds the main runtime context renderer after bootstrap delegation.
- No committed evidence transcripts containing local/private paths; `evidence/` is ignored by `.gitignore:7`.
- No task is complete with tests only; each task also needs CLI transcript evidence.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD + pytest, with subprocess CLI tests, `tmp_path`, and capture patterns from `tests/test_package_import.py:24-42`, `tests/test_onboarding_validation.py:10-43`, and pytest official docs.
- QA policy: every task has agent-executed scenarios
- Evidence: `evidence/task-<N>-harness-v1.<ext>`

## Execution strategy
### Parallel execution waves
> Target 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks to maximize parallelism.

Wave 1 (no dependencies):
- Task 1: Public-safe fixtures and CLI evidence capture
- Task 2: CLI router and command base
- Task 3: Runtime profile boundary and state IO

Wave 2 (after Wave 1):
- Task 4: depends [1, 2, 3]
- Task 5: depends [1, 2, 3]

Wave 3 (after Wave 2):
- Task 6: depends [4, 5]
- Task 7: depends [4, 5, 6]

Wave 4 (after Wave 3):
- Task 8: depends [6, 7]

Critical path: Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 6 -> Task 7 -> Task 8

### Dependency matrix
| Task | Depends on | Blocks | Can parallelize with |
|------|------------|--------|----------------------|
| 1    | none       | 4, 5   | 2, 3                 |
| 2    | none       | 4, 5, 6, 7, 8 | 1, 3          |
| 3    | none       | 4, 5, 6, 7, 8 | 1, 2          |
| 4    | 1, 2, 3    | 6, 7, 8 | 5                   |
| 5    | 1, 2, 3    | 6, 7, 8 | 4                   |
| 6    | 4, 5       | 7, 8   | none                 |
| 7    | 4, 5, 6    | 8      | none                 |
| 8    | 6, 7       | final  | none                 |

## Todos
> Implementation + Test = ONE task. Never separate.
> Every task MUST have: References + Acceptance Criteria + QA Scenarios + Commit.

- [ ] 1. Public-safe fixtures and CLI evidence capture

  What to do: Add public-safe harness fixtures, temp-profile helpers, privacy test coverage, and `scripts/qa/capture-command.ps1`. The wrapper must record scenario name, command, working directory, exit code, stdout, stderr, start/end timestamps, and cleanup notes. Extend `.gitignore` and privacy tests if new local temp folders are introduced.
  Must NOT do: Do not commit real CLI evidence, private profile output, real reports, local DBs, or fixture names that match private-data scanners.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4, 5] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `AGENTS.md:7-11` - Codex Desktop runtime, public-safe data boundary, tests-before-implementation rule.
  - Pattern:  `AGENTS.md:15-20` - public repo vs private profile workspace boundary.
  - Pattern:  `.gitignore:1-8` - existing ignored private/local artifact patterns, including `evidence/`.
  - Pattern:  `tests/test_repo_privacy.py:43-77` - forbidden text/path scanner to extend for harness artifacts.
  - Pattern:  `tests/test_onboarding_validation.py:10-43` - subprocess JSON failure and redaction pattern.
  - External: `https://docs.pytest.org/en/stable/how-to/tmp_path.html` - pytest `tmp_path` filesystem test pattern.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_qa_capture.py tests/test_repo_privacy.py -q` fails on the new capture/privacy tests and writes `evidence/task-1-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_qa_capture.py tests/test_repo_privacy.py -q` exits 0 and writes `evidence/task-1-harness-v1.txt`.
  - [ ] `scripts/qa/capture-command.ps1` captures both successful and failing commands without changing their exit codes.
  - [ ] `uv run pytest tests/test_package_import.py tests/test_repo_privacy.py -q` exits 0.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: capture wrapper records a successful CLI command
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-1-version -Command 'uv run python -m chat_lms_agent --version' -Evidence evidence/task-1-harness-v1.txt
    Expected: evidence file exists, exit_code is 0, stdout contains chat-lms-agent, stderr is recorded
    Evidence: evidence/task-1-harness-v1.txt

  Scenario: capture wrapper preserves failing command exit
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-1-failure -Command 'uv run python -m chat_lms_agent definitely-unknown --json' -Evidence evidence/task-1-harness-v1-error.txt
    Expected: wrapper exits nonzero and evidence records the child exit code plus stderr/stdout without traceback
    Evidence: evidence/task-1-harness-v1-error.txt
  ```

  Commit: YES | Message: `test(qa): add public-safe harness evidence capture` | Files: [`scripts/qa/capture-command.ps1`, `tests/test_qa_capture.py`, `tests/test_repo_privacy.py`, `tests/fixtures/harness/*`, `.gitignore`]

- [ ] 2. CLI router and command base

  What to do: Keep `src/chat_lms_agent/cli.py` as the thin entrypoint and add `src/chat_lms_agent/commands/` modules for command registration, JSON output, error handling, exit code constants, and existing `doctor`, `context`, and `onboarding` routes. Use stdlib `argparse`. Unknown commands and flags must return exit code `2`; with `--json`, they must emit machine-readable error JSON. Preserve `--version` and console script behavior.
  Must NOT do: Do not add Click, Typer, or runtime dependencies. Do not change onboarding behavior beyond routing compatibility.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4, 5, 6, 7, 8] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/cli.py:16-23` - existing help text surface to replace with generated command help.
  - Pattern:  `src/chat_lms_agent/cli.py:26-42` - current string-matching router and unknown-command exit.
  - Pattern:  `src/chat_lms_agent/cli.py:45-46` - `app()` must remain console script entrypoint.
  - Pattern:  `src/chat_lms_agent/__main__.py:1-5` - module execution path must remain valid.
  - Pattern:  `tests/test_package_import.py:10-42` - import and module invocation contract.
  - Pattern:  `tests/test_doctor.py:41-51` - subprocess helper style.
  - API/Type: `pyproject.toml:16-17` - installed `chat-lms` console script.
  - External: `https://docs.python.org/3/library/argparse.html` - stdlib parser/subparser behavior.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_cli_contract.py -q` fails on invalid flag and command-tree tests and writes `evidence/task-2-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_cli_contract.py tests/test_package_import.py tests/test_onboarding_validation.py -q` exits 0 and writes `evidence/task-2-harness-v1.txt`.
  - [ ] `uv run python -m chat_lms_agent --help` lists `doctor`, `context`, `profile`, `tool`, `memory`, `hook`, `session`, `bootstrap`, and `onboarding`.
  - [ ] `uv run python -m chat_lms_agent doctor --totally-invalid --json` exits 2 with JSON error code `INVALID_ARGUMENT`.
  - [ ] `uv run chat-lms --version` exits 0 and prints `chat-lms-agent`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: help exposes the full harness command tree
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-2-help -Command 'uv run python -m chat_lms_agent --help' -Evidence evidence/task-2-harness-v1.txt
    Expected: exit code 0 and output contains doctor, context, profile, tool, memory, hook, session, bootstrap, onboarding
    Evidence: evidence/task-2-harness-v1.txt

  Scenario: invalid doctor flag is rejected as a contract error
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-2-invalid-doctor -Command 'uv run python -m chat_lms_agent doctor --totally-invalid --json' -Evidence evidence/task-2-harness-v1-error.txt
    Expected: exit code 2 and JSON error.code is INVALID_ARGUMENT with no traceback
    Evidence: evidence/task-2-harness-v1-error.txt
  ```

  Commit: YES | Message: `refactor(cli): add explicit harness command router` | Files: [`src/chat_lms_agent/cli.py`, `src/chat_lms_agent/commands/__init__.py`, `src/chat_lms_agent/commands/base.py`, `src/chat_lms_agent/commands/doctor.py`, `src/chat_lms_agent/commands/context.py`, `src/chat_lms_agent/commands/onboarding.py`, `tests/test_cli_contract.py`, `tests/test_package_import.py`, `tests/test_onboarding_validation.py`]

- [ ] 3. Runtime profile boundary and state IO

  What to do: Add `src/chat_lms_agent/runtime/` for profile resolution, public-repo boundary detection, redaction, atomic JSON writes, lock files, fixture/temp profile mapping, and `profile inspect`. State paths must resolve to explicit temp/private roots, never implicit public repo paths. Tests use `tmp_path`; CLI QA uses `$env:TEMP` roots.
  Must NOT do: Do not inspect real private profile folders. Do not create state files under the public repository except within pytest temp dirs.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4, 5, 6, 7, 8] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `AGENTS.md:15-20` - product code belongs in repo; runtime data belongs outside repo.
  - Pattern:  `docs/runtime-boundary.md:18-31` - public repo must not hold real runtime data.
  - Pattern:  `docs/runtime-boundary.md:33-43` - bootstrap creates private workspace and must not perform destructive/runtime data actions automatically.
  - Pattern:  `scripts/bootstrap.ps1:14-31` - existing profile path categories to preserve conceptually.
  - Pattern:  `tests/test_bootstrap.py:33-62` - current user-mode dry-run private workspace assertions.
  - Pattern:  `tests/test_repo_privacy.py:80-90` - ignored local artifact patterns.
  - External: `https://docs.pytest.org/en/stable/how-to/tmp_path.html` - temp directory tests.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_runtime_profile.py -q` fails on public-repo rejection and atomic write tests and writes `evidence/task-3-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_runtime_profile.py tests/test_repo_privacy.py -q` exits 0 and writes `evidence/task-3-harness-v1.txt`.
  - [ ] `profile inspect --profile-root . --json` exits 4 with error code `PUBLIC_REPO_STATE_REJECTED`.
  - [ ] Atomic write tests prove no partial JSON file remains after a simulated write failure.
  - [ ] Redaction tests remove private paths and credential-like values from JSON output.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: temp profile root is accepted and inspected
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-3-profile-temp -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-3-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent profile inspect --profile-root $root --json' -Evidence evidence/task-3-harness-v1.txt
    Expected: exit code 0 and JSON state paths are under the temp root with redacted display paths
    Evidence: evidence/task-3-harness-v1.txt

  Scenario: public repo root is rejected
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-3-profile-public-reject -Command 'uv run python -m chat_lms_agent profile inspect --profile-root . --json' -Evidence evidence/task-3-harness-v1-error.txt
    Expected: exit code 4 and JSON error.code is PUBLIC_REPO_STATE_REJECTED
    Evidence: evidence/task-3-harness-v1-error.txt
  ```

  Commit: YES | Message: `feat(runtime): enforce private profile state boundary` | Files: [`src/chat_lms_agent/runtime/__init__.py`, `src/chat_lms_agent/runtime/paths.py`, `src/chat_lms_agent/runtime/state.py`, `src/chat_lms_agent/runtime/redaction.py`, `src/chat_lms_agent/commands/profile.py`, `tests/test_runtime_profile.py`, `tests/fixtures/harness/*`]

- [ ] 4. Tool registry lifecycle

  What to do: Implement tool registry models, validators, state persistence, and CLI commands: `tool draft`, `tool validate`, `tool activate`, `tool list`, `tool show`, `tool deprecate`, `tool scaffold`, `tool materialize-plan`, and `tool promote`. Tool kinds for v1 are `query_template`, `action_template`, `workflow`, and `module_command`. Safe data-driven tools may promote; `module_command` requires explicit reviewed implementation/test references and must otherwise return exit code `3`.
  Must NOT do: Do not implement delete. Do not execute arbitrary generated Python code. Do not allow unreviewed `module_command` activation.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [6, 7, 8] | Blocked by: [1, 2, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `plans/chat-lms-agent-self-maintaining-harness.md:27-40` - tools vs memory, lifecycle, storage, safe self-creation defaults.
  - Pattern:  `plans/chat-lms-agent-self-maintaining-harness.md:222-254` - intended tool lifecycle commands and QA contract.
  - Pattern:  `src/chat_lms_agent/doctor.py:11-27` - dataclass/TyperDict payload style to reuse for small typed reports.
  - Pattern:  `src/chat_lms_agent/cli.py:57-69` - existing JSON output flow to replace through command base.
  - API/Type: `src/chat_lms_agent/runtime/state.py` - Task 3 state IO contract.
  - External: `https://docs.python.org/3/library/json.html` - JSON persistence/parse behavior.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_tool_registry.py tests/test_tool_self_create.py -q` fails on draft/activate/scaffold contracts and writes `evidence/task-4-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_tool_registry.py tests/test_tool_self_create.py tests/test_runtime_profile.py -q` exits 0 and writes `evidence/task-4-harness-v1.txt`.
  - [ ] `tool draft -> tool activate -> tool list --json -> tool show --json -> tool deprecate` round-trips using a temp profile.
  - [ ] `tool promote` for unreviewed `module_command` exits 3 with status `NEEDS_REVIEW`.
  - [ ] Registry list output is deterministic and sorted.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: safe query tool lifecycle round-trip
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-4-tool-roundtrip -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-4-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent tool draft --profile-root $root --from tests/fixtures/harness/tool-query-template.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool activate --profile-root $root --name sample_lookup --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool list --profile-root $root --json }' -Evidence evidence/task-4-harness-v1.txt
    Expected: final JSON contains active sample_lookup with kind query_template and no private path leakage
    Evidence: evidence/task-4-harness-v1.txt

  Scenario: unreviewed module command cannot promote
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-4-module-review -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-4-module-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent tool scaffold --profile-root $root --from tests/fixtures/harness/tool-request-module.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool promote --profile-root $root --name sample_module_tool --json }' -Evidence evidence/task-4-harness-v1-error.txt
    Expected: exit code 3 and JSON status is NEEDS_REVIEW; tool remains inactive
    Evidence: evidence/task-4-harness-v1-error.txt
  ```

  Commit: YES | Message: `feat(tool): add durable tool registry lifecycle` | Files: [`src/chat_lms_agent/registry/__init__.py`, `src/chat_lms_agent/registry/models.py`, `src/chat_lms_agent/registry/store.py`, `src/chat_lms_agent/registry/validators.py`, `src/chat_lms_agent/commands/tool.py`, `tests/test_tool_registry.py`, `tests/test_tool_self_create.py`, `tests/fixtures/harness/tool-*.json`]

- [ ] 5. Memory and decision lifecycle

  What to do: Implement memory and decision record models, persistence, validators, and CLI commands: `memory upsert`, `memory list`, `memory compact`, `memory archive`, and decision record writes used by tool scaffold/promote and closeout. Supported scopes are `workspace`, `session`, and `entity`. Upserts by `memory_key` replace existing entries. Store concise summaries and evidence refs, not raw prompts.
  Must NOT do: Do not persist raw prompt text, private paths, credential-like values, or duplicate memories for the same scope/key.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [6, 7, 8] | Blocked by: [1, 2, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `plans/chat-lms-agent-self-maintaining-harness.md:27-29` - memory and tools are separate concepts.
  - Pattern:  `plans/chat-lms-agent-self-maintaining-harness.md:256-288` - intended memory lifecycle and QA contract.
  - Pattern:  `src/chat_lms_agent/context.py:9-17` - static context output to feed with memory later.
  - Pattern:  `tests/test_hooks.py:20-47` - redaction assertion for hydrated context.
  - API/Type: `src/chat_lms_agent/runtime/redaction.py` - Task 3 redaction contract.
  - External: `https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html` - stdout/stderr capture for direct command tests.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_memory_registry.py -q` fails on upsert/scope/redaction tests and writes `evidence/task-5-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_memory_registry.py tests/test_runtime_profile.py tests/test_repo_privacy.py -q` exits 0 and writes `evidence/task-5-harness-v1.txt`.
  - [ ] Repeated `memory upsert` with same scope/scope-key/memory-key leaves exactly one record with the newer summary.
  - [ ] Entity-scoped memory is excluded unless hydration receives matching entity context.
  - [ ] Unsafe memory input exits 4 or stores only redacted content.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: memory upsert replaces an existing key
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-5-memory-replace -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-5-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent memory upsert --profile-root $root --scope workspace --scope-key tutoring --memory-key billing_rule --summary first --evidence-ref evidence/sample.txt --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory upsert --profile-root $root --scope workspace --scope-key tutoring --memory-key billing_rule --summary second --evidence-ref evidence/sample.txt --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory list --profile-root $root --json }' -Evidence evidence/task-5-harness-v1.txt
    Expected: list JSON has exactly one billing_rule memory and summary is second
    Evidence: evidence/task-5-harness-v1.txt

  Scenario: unsafe memory text is rejected or redacted
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-5-memory-unsafe -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-5-unsafe-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent memory upsert --profile-root $root --scope workspace --scope-key tutoring --memory-key unsafe --summary "credential-like-value" --json' -Evidence evidence/task-5-harness-v1-error.txt
    Expected: exit code 4 or stored JSON contains only redacted content; evidence contains no raw private value
    Evidence: evidence/task-5-harness-v1-error.txt
  ```

  Commit: YES | Message: `feat(memory): add scoped memory and decision records` | Files: [`src/chat_lms_agent/memory/__init__.py`, `src/chat_lms_agent/memory/models.py`, `src/chat_lms_agent/memory/store.py`, `src/chat_lms_agent/commands/memory.py`, `tests/test_memory_registry.py`, `tests/fixtures/harness/memory-*.json`]

- [ ] 6. Context hydration from registry and memory

  What to do: Replace `build_codex_context` with a profile-aware snapshot builder and command surface. `context hydrate --for-codex --json` must return deterministic JSON containing active tool summaries, command hints, relevant memory summaries, profile health, warnings, and closeout obligations. Non-JSON hook mode must produce Codex `hookSpecificOutput.additionalContext`. Keep payload concise and redacted.
  Must NOT do: Do not dump full registry/memory files into context. Do not expose private paths, credentials, raw prompt text, or malformed registry tracebacks.

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [7, 8] | Blocked by: [4, 5]

  References (executor has NO interview context - be exhaustive):
  - Current:  `src/chat_lms_agent/context.py:9-17` - static placeholder context to replace.
  - Pattern:  `tests/test_hooks.py:20-47` - subprocess context hydrate and redaction checks.
  - Pattern:  `hooks/hooks.json:1-5` - SessionStart currently calls context hydrate.
  - Pattern:  `plans/chat-lms-agent-self-maintaining-harness.md:292-322` - intended hydration contract.
  - API/Type: `src/chat_lms_agent/registry/store.py` - active tool snapshot contract.
  - API/Type: `src/chat_lms_agent/memory/store.py` - scoped memory retrieval contract.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_context_hydration.py tests/test_hooks.py -q` fails on tool/memory hydration tests and writes `evidence/task-6-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_context_hydration.py tests/test_hooks.py tests/test_tool_registry.py tests/test_memory_registry.py -q` exits 0 and writes `evidence/task-6-harness-v1.txt`.
  - [ ] Hydration includes active tool command hints and relevant memories from a temp profile.
  - [ ] Malformed registry/memory fixture returns warning code `REGISTRY_PARTIAL_LOAD` or `MEMORY_PARTIAL_LOAD` without traceback.
  - [ ] Hydrated payload does not include private temp root strings or unsafe values.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: hydrate includes active tool inventory and scoped memory
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-6-context-hydrate -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-6-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent tool draft --profile-root $root --from tests/fixtures/harness/tool-query-template.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool activate --profile-root $root --name sample_lookup --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory upsert --profile-root $root --scope workspace --scope-key tutoring --memory-key billing_rule --summary "Use public-safe sample summaries only." --evidence-ref evidence/sample.txt --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent context hydrate --for-codex --profile-root $root --json }' -Evidence evidence/task-6-harness-v1.txt
    Expected: JSON contains tools array with sample_lookup command_hint and memories array with billing_rule summary
    Evidence: evidence/task-6-harness-v1.txt

  Scenario: malformed state warns without crashing
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-6-context-malformed -Command 'uv run python -m chat_lms_agent context hydrate --for-codex --profile-root tests/fixtures/harness/malformed-profile --json' -Evidence evidence/task-6-harness-v1-error.txt
    Expected: exit code 0, warnings include partial-load code, stderr has no Traceback
    Evidence: evidence/task-6-harness-v1-error.txt
  ```

  Commit: YES | Message: `feat(context): hydrate tools and memory for Codex` | Files: [`src/chat_lms_agent/context.py`, `src/chat_lms_agent/commands/context.py`, `tests/test_context_hydration.py`, `tests/test_hooks.py`, `tests/fixtures/harness/*`]

- [ ] 7. Hook commands and closeout verification

  What to do: Implement `hook session-start`, `hook user-prompt-submit`, `hook post-tool-use`, `hook post-compact`, `hook stop`, and `session closeout --verify-memory`. Hook commands must accept stdin JSON, tolerate malformed payloads, and emit Codex-compatible output. Closeout must inspect tool, memory, and decision records; satisfied state exits 0, missing obligations exit 5 with machine-readable details. Update `hooks/hooks.json` to call stable hook commands.
  Must NOT do: Do not silently pass unknown obligations. Do not write vague memory summaries. Do not remove Stop blocking behavior when obligations are missing.

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [8] | Blocked by: [4, 5, 6]

  References (executor has NO interview context - be exhaustive):
  - Current:  `hooks/hooks.json:1-10` - SessionStart and Stop hook commands, including unimplemented closeout.
  - Current:  `src/chat_lms_agent/cli.py:40-42` - unknown command exit currently catches `session closeout`.
  - Pattern:  `tests/test_hooks.py:10-47` - existing hook registration and redaction tests to expand.
  - Pattern:  `plans/chat-lms-agent-self-maintaining-harness.md:326-356` - intended hook command package.
  - Pattern:  `plans/chat-lms-agent-self-maintaining-harness.md:462-492` - intended closeout contract.
  - API/Type: `src/chat_lms_agent/context.py` - Task 6 hydration contract.
  - API/Type: `src/chat_lms_agent/memory/store.py` - Task 5 memory/decision contract.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_hooks.py tests/test_session_closeout.py -q` fails on registered command execution and closeout tests and writes `evidence/task-7-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_hooks.py tests/test_session_closeout.py tests/test_context_hydration.py -q` exits 0 and writes `evidence/task-7-harness-v1.txt`.
  - [ ] Every command in `hooks/hooks.json` executes against fixture/stdin payloads.
  - [ ] `session closeout --verify-memory --json` exits 0 for complete temp profile state and 5 for missing memory/decision obligations.
  - [ ] Malformed hook stdin exits gracefully with JSON warning or safe no-op output and no traceback.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: SessionStart hook injects hydrated context
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-7-session-start -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-7-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; Get-Content tests/fixtures/harness/hook-session-start.json | uv run python -m chat_lms_agent hook session-start --profile-root $root' -Evidence evidence/task-7-harness-v1.txt
    Expected: exit code 0 and JSON contains hookSpecificOutput.additionalContext
    Evidence: evidence/task-7-harness-v1.txt

  Scenario: Stop hook blocks missing durable memory
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-7-stop-block -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-7-block-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent tool draft --profile-root $root --from tests/fixtures/harness/tool-query-template.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool activate --profile-root $root --name sample_lookup --json }; if ($LASTEXITCODE -eq 0) { Get-Content tests/fixtures/harness/hook-stop.json | uv run python -m chat_lms_agent hook stop --profile-root $root }' -Evidence evidence/task-7-harness-v1-error.txt
    Expected: exit code 5 or hook JSON decision blocks stop with missing memory obligation
    Evidence: evidence/task-7-harness-v1-error.txt
  ```

  Commit: YES | Message: `feat(hooks): verify memory at session closeout` | Files: [`src/chat_lms_agent/commands/hook.py`, `src/chat_lms_agent/commands/session.py`, `hooks/hooks.json`, `tests/test_hooks.py`, `tests/test_session_closeout.py`, `tests/fixtures/harness/hook-*.json`]

- [ ] 8. Doctor checks and bootstrap delegation

  What to do: Expand doctor to validate parser availability, hook command executability, registry integrity, memory integrity, private state boundary, redaction, closeout readiness, and bootstrap generated files. Add `bootstrap plan`, `bootstrap apply`, and `bootstrap sync-runtime` Python commands. Refactor `scripts/bootstrap.ps1` to parse arguments and delegate to the Python CLI, while preserving dry-run/user-mode semantics with temp environment override support.
  Must NOT do: Do not write real user profile paths during tests. Do not print private paths or unsafe values in doctor/bootstrap output. Do not claim `DONE action=run doctor` unless doctor actually ran.

  Parallelization: Can parallel: NO | Wave 4 | Blocks: [final] | Blocked by: [6, 7]

  References (executor has NO interview context - be exhaustive):
  - Current:  `src/chat_lms_agent/doctor.py:29-73` - current path-only doctor checks.
  - Pattern:  `tests/test_doctor.py:10-38` - JSON status and redaction contract.
  - Current:  `scripts/bootstrap.ps1:33-413` - PowerShell currently owns private workspace and hook generation.
  - Current:  `scripts/bootstrap.ps1:489-512` - dry-run and DONE output behavior to preserve/fix.
  - Pattern:  `tests/test_bootstrap.py:7-62` - current bootstrap dry-run expectations.
  - Pattern:  `README.md:31-44` - private workspace bootstrap and safe sync user-facing contract.
  - External: `https://docs.astral.sh/uv/reference/cli/#uv-run` - `uv run` project command invocation.
  - External: `https://docs.astral.sh/ruff/linter/` - Ruff CLI gate.
  - External: `https://docs.basedpyright.com/v1.29.4/configuration/command-line/` - basedpyright CLI gate.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before implementation: `uv run pytest tests/test_doctor.py tests/test_bootstrap.py -q` fails on executable hook/registry/bootstrap delegation tests and writes `evidence/task-8-harness-v1-red.txt`.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_doctor.py tests/test_bootstrap.py tests/test_hooks.py tests/test_session_closeout.py -q` exits 0 and writes `evidence/task-8-harness-v1.txt`.
  - [ ] `doctor --repair --profile-root <temp> --json` includes checks for parser, hooks, registry, memory, profile boundary, closeout, and bootstrap.
  - [ ] Broken hook fixture makes doctor exit nonzero with a hook executable failure.
  - [ ] Bootstrap dry-run delegates to Python plan output and does not claim unrun commands as done.
  - [ ] Bootstrap temp user mode writes generated private workspace files under temp env roots only.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: doctor validates a healthy temp profile
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-8-doctor-pass -Command '$root = Join-Path $env:TEMP "chat-lms-agent-task-8-profile"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent doctor --repair --profile-root $root --json' -Evidence evidence/task-8-harness-v1.txt
    Expected: exit code 0 and checks include parser, hooks, registry, memory, profile_boundary, closeout, bootstrap
    Evidence: evidence/task-8-harness-v1.txt

  Scenario: bootstrap dry-run does not claim unrun doctor
    Tool:     powershell
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-8-bootstrap-dry-run -Command '$local = Join-Path $env:TEMP "chat-lms-agent-task-8-local"; $roaming = Join-Path $env:TEMP "chat-lms-agent-task-8-roaming"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $local,$roaming; $env:LOCALAPPDATA=$local; $env:APPDATA=$roaming; powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -DryRun -Mode User -Profile sample' -Evidence evidence/task-8-harness-v1-error.txt
    Expected: exit code 0, output lists delegated Python commands, and no DONE line claims doctor ran
    Evidence: evidence/task-8-harness-v1-error.txt
  ```

  Commit: YES | Message: `refactor(bootstrap): delegate harness setup to Python CLI` | Files: [`src/chat_lms_agent/doctor.py`, `src/chat_lms_agent/commands/doctor.py`, `src/chat_lms_agent/commands/bootstrap.py`, `scripts/bootstrap.ps1`, `tests/test_doctor.py`, `tests/test_bootstrap.py`]

## Final verification wave (MANDATORY - after all implementation tasks)
> Runs in PARALLEL. ALL must APPROVE. Surface results to the caller and wait for an explicit "okay" before declaring complete.
- [ ] F1. Plan compliance audit - every task done, every acceptance criterion met
  - Command: `uv run pytest -q`
  - Evidence: `evidence/final-harness-v1-pytest.txt`
  - Approval condition: every planned test file exists, every named acceptance test passes, and the evidence ledger has RED/GREEN entries for Tasks 1-8.
- [ ] F2. Code quality review - diagnostics clean, idioms match, no dead code
  - Command: `uv run ruff check .`
  - Command: `uv run basedpyright`
  - Evidence: `evidence/final-harness-v1-ruff.txt`
  - Evidence: `evidence/final-harness-v1-basedpyright.txt`
  - Approval condition: both commands exit 0; no edited Python file exceeds 250 pure LOC unless the reviewer records a specific exception.
- [ ] F3. Real manual QA - every QA scenario executed with evidence captured
  - Command: `powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name final-c001-happy-cli -Command '$root = Join-Path $env:TEMP "chat-lms-agent-final-c001"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent tool draft --profile-root $root --from tests/fixtures/harness/tool-query-template.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool activate --profile-root $root --name sample_lookup --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory upsert --profile-root $root --scope workspace --scope-key tutoring --memory-key tool_sample_lookup --summary "sample_lookup is active for public-safe query templates." --evidence-ref evidence/task-4-harness-v1.txt --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool list --profile-root $root --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent memory list --profile-root $root --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent context hydrate --for-codex --profile-root $root --json }; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent session closeout --verify-memory --profile-root $root --json }; if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath ".chat-lms-state")) { Write-Error "repo state directory created"; exit 4 }' -Evidence .omo/ulw-loop/evidence/G001-C001-happy-cli.txt`
  - Command: `powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name final-c002-adversarial-cli -Command '$root = Join-Path $env:TEMP "chat-lms-agent-final-c002"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; uv run python -m chat_lms_agent doctor --invalid-flag --json; $doctor = $LASTEXITCODE; uv run python -m chat_lms_agent tool activate --profile-root $root --name missing_tool --json; $missing = $LASTEXITCODE; uv run python -m chat_lms_agent profile inspect --profile-root . --json; $public = $LASTEXITCODE; uv run python -m chat_lms_agent tool draft --profile-root $root --from tests/fixtures/harness/tool-query-template.json --json; if ($LASTEXITCODE -eq 0) { uv run python -m chat_lms_agent tool activate --profile-root $root --name sample_lookup --json }; uv run python -m chat_lms_agent session closeout --verify-memory --profile-root $root --json; $closeout = $LASTEXITCODE; if ($doctor -ne 2 -or $missing -ne 2 -or $public -ne 4 -or $closeout -ne 5) { Write-Error "unexpected exit codes doctor=$doctor missing=$missing public=$public closeout=$closeout"; exit 1 }' -Evidence .omo/ulw-loop/evidence/G001-C002-adversarial-cli.txt`
  - Command: `powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name final-c003-hooks-tests -Command '$root = Join-Path $env:TEMP "chat-lms-agent-final-c003"; Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root; Get-Content tests/fixtures/harness/hook-session-start.json | uv run python -m chat_lms_agent hook session-start --profile-root $root; if ($LASTEXITCODE -eq 0) { Get-Content tests/fixtures/harness/hook-user-prompt-submit.json | uv run python -m chat_lms_agent hook user-prompt-submit --profile-root $root }; if ($LASTEXITCODE -eq 0) { Get-Content tests/fixtures/harness/hook-post-tool-use.json | uv run python -m chat_lms_agent hook post-tool-use --profile-root $root }; if ($LASTEXITCODE -eq 0) { Get-Content tests/fixtures/harness/hook-post-compact.json | uv run python -m chat_lms_agent hook post-compact --profile-root $root }; if ($LASTEXITCODE -eq 0) { Get-Content tests/fixtures/harness/hook-stop-complete.json | uv run python -m chat_lms_agent hook stop --profile-root $root }; if ($LASTEXITCODE -eq 0) { uv run pytest tests/test_package_import.py tests/test_repo_privacy.py tests/test_hooks.py -q }; if ($LASTEXITCODE -eq 0) { uv run ruff check . }; if ($LASTEXITCODE -eq 0) { uv run basedpyright }; if ($LASTEXITCODE -eq 0) { uv run pytest -q }' -Evidence .omo/ulw-loop/evidence/G001-C003-regression-hooks-tests.txt`
  - Approval condition: C001 proves happy lifecycle JSON success, C002 proves exit codes 2/4/5 with JSON explanations, and C003 proves every hook command is executable.
- [ ] F4. Scope fidelity - nothing extra shipped beyond Must-Have, nothing Must-NOT-Have introduced
  - Command: `uv run pytest tests/test_repo_privacy.py tests/test_bootstrap.py tests/test_hooks.py -q`
  - Evidence: `evidence/final-harness-v1-scope.txt`
  - Approval condition: public-repo privacy stays clean, bootstrap writes only temp/private targets during tests, and hooks contain stable CLI commands only.

## Commit strategy
- One logical change per commit. Conventional Commits (`<type>(<scope>): <subject>` body + footer).
- Atomic: every commit builds and passes tests on its own.
- No "WIP" / "fix typo squash later" commits on the final branch - clean up before merge.
- Reference the plan file path in the final commit footer: `Plan: plans/chat-lms-agent-harness-v1-wave-plan.md`.

## Success criteria
- All Must-Have shipped; all QA scenarios pass with captured evidence; F1-F4 approved; commit history clean.
- `uv run pytest -q` exits 0 and evidence is captured to `evidence/final-harness-v1-pytest.txt`.
- `uv run ruff check .` exits 0 and evidence is captured to `evidence/final-harness-v1-ruff.txt`.
- `uv run basedpyright` exits 0 and evidence is captured to `evidence/final-harness-v1-basedpyright.txt`.
- C001 happy CLI lifecycle evidence is captured to `.omo/ulw-loop/evidence/G001-C001-happy-cli.txt` using a temp private profile root and proves no repo state directory is created.
- C002 adversarial CLI/boundary/closeout evidence is captured to `.omo/ulw-loop/evidence/G001-C002-adversarial-cli.txt` and proves exit codes `2`, `4`, and `5` with JSON explanations.
- C003 hook/test regression evidence is captured to `.omo/ulw-loop/evidence/G001-C003-regression-hooks-tests.txt` and proves every command in `hooks/hooks.json` is executable.
