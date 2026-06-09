# Harness Strengthening Implementation

## TL;DR
> Summary:      Strengthen the existing public-safe Chat LMS Agent harness by adding the `agent-tools` registry surface, proposal validation, memory-obligation enforcement, context hydration fields, and doctor checks without replacing current `tool`, `memory`, `hook`, or `side-panel` contracts.
> Deliverables:
> - `agent-tools list --json` and `agent-tools validate --from <path> --json`
> - Shared agent-tool registry, proposal validator, and memory-obligation checker
> - Hook changed-files enforcement for registry/tool changes without memory
> - Hydrated `agent_tools`, `tool_registry`, and `memory_policy`
> - Doctor check for `agent_tools` registry readiness
> Effort:       Medium
> Risk:         Medium - multiple CLI, hook, context, doctor, and state surfaces must change while preserving existing side-panel contracts.

## Scope
### Must have
- Add TDD RED tests before production code for every task.
- Preserve existing parser, dispatcher, JSON, and exit-code conventions from `src/chat_lms_agent/command_parser.py:25`, `src/chat_lms_agent/commands.py:33`, `src/chat_lms_agent/commands.py:73`, and `src/chat_lms_agent/tool_handlers.py:149`.
- Keep profile runtime state under `.chat-lms-state` as established by `src/chat_lms_agent/state.py:15`, `src/chat_lms_agent/state.py:63`, and `src/chat_lms_agent/state.py:83`.
- `uv run python -m chat_lms_agent agent-tools list --json` exits `0`, returns `status: PASS`, and includes `side-panel`, `academy-db`, and `memory_obligation`.
- `uv run python -m chat_lms_agent agent-tools validate --from tests/fixtures/agent_tools/malformed-missing-memory-command.json --json` exits `2` and returns `MISSING_MEMORY_OBLIGATION` plus `MISSING_COMMAND_CONTRACT`.
- `uv run python -m chat_lms_agent hook post-tool-use --changed-files src/chat_lms_agent/agent_tools.py --json` exits nonzero and returns `MEMORY_UPDATE_REQUIRED`.
- `context hydrate --for-codex --json` includes `agent_tools`, `memory_policy`, and `tool_registry` while preserving `active_tools`, `memory`, and `side_panel` from `src/chat_lms_agent/context.py:23`.
- `doctor --repair --json` includes doctor check ID `agent_tools`; the `agent_tools` check must be `PASS`.
- Existing side-panel contracts stay green, especially `tests/test_context_hydration.py:10`, `tests/test_side_panel_contract.py:17`, and `tests/test_side_panel_contract.py:74`.
- Every implementation task is executed by a coding agent and independently verified by a QA/testing agent. If tmux is unavailable in the Windows Codex Desktop runtime, capture equivalent PowerShell CLI transcripts.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not add real learner records, generated reports, secrets, private profile paths, or local memory to the public repo.
- Do not use the public repo root as runtime profile state; preserve `PUBLIC_REPO_STATE_REJECTED` behavior from `src/chat_lms_agent/state.py:58` and `tests/test_harness_contracts.py:45`.
- Do not remove or rename existing `tool`, `memory`, `session`, `hook`, `doctor`, `context`, or `side-panel` commands.
- Do not create a real academy database or connect to external LMS systems; `academy-db` is a registry entry only in this scope.
- Do not replace the side-panel contract shape from `src/chat_lms_agent/side_panel.py:89`.
- Do not rely on user manual testing; all checks must be agent-executed and captured.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD + pytest. Use `tmp_path`/isolated profile roots for state and subprocess CLI tests following pytest temporary-path and capture guidance from `https://docs.pytest.org/en/stable/how-to/tmp_path.html` and `https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html`.
- QA policy: every task has agent-executed scenarios. Use `scripts/qa/capture-command.ps1:1` to capture command, stdout, stderr, exit code, and cleanup receipt.
- Evidence: `evidence/task-<N>-<slug>.<ext>`

## Execution strategy
### Parallel execution waves
> Target 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks to maximize parallelism.

Wave 1 (no dependencies):
- Task 1: agent-tool registry model and default inventory
- Task 2: proposal validation core
- Task 3: memory-obligation core

Wave 2 (after Wave 1):
- Task 4: depends [1, 2, 3]
- Task 5: depends [1, 3]
- Task 6: depends [1, 3]

Critical path: Task 1 -> Task 4 -> Final verification

### Dependency matrix
| Task | Depends on | Blocks | Can parallelize with |
|------|------------|--------|----------------------|
| 1    | none       | 4, 5, 6 | 2, 3 |
| 2    | none       | 4 | 1, 3 |
| 3    | none       | 4, 5, 6 | 1, 2 |
| 4    | 1, 2, 3    | F1, F3 | 5, 6 |
| 5    | 1, 3       | F1, F3 | 4, 6 |
| 6    | 1, 3       | F1, F2 | 4, 5 |

## Todos
> Implementation + Test = ONE task. Never separate.
> Every task MUST have: References + Acceptance Criteria + QA Scenarios + Commit.

- [ ] 1. Agent-tool registry model and default inventory

  What to do: Add a small typed registry module, preferably `src/chat_lms_agent/agent_tools.py`, that returns a deterministic default inventory with at least `side-panel`, `academy-db`, and `memory_obligation`. Include fields required by validation and hydration: `name`, `kind`, `summary`, `command_contract`, `memory_obligation`, `status`, and `source`. Add RED tests first in `tests/test_agent_tools_registry.py` asserting the inventory names, sort order, redaction behavior, and that `academy-db` is marked as registry/discovery only unless a future DB implementation exists.
  Must NOT do: Do not persist default inventory into real profile state; do not create DB files; do not remove the legacy `tool` registry.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4, 5, 6] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/state.py:15` - profile runtime files live under `.chat-lms-state`.
  - Pattern:  `src/chat_lms_agent/state.py:63` - existing registries load deterministic, sorted, redacted payloads.
  - Pattern:  `src/chat_lms_agent/state.py:105` - use the existing redaction helper for secret-like text.
  - API/Type: `src/chat_lms_agent/state.py:20` - mirror the local TypedDict style for registry payloads.
  - Test:     `tests/test_harness_contracts.py:37` - fixture profile tests assert deterministic tool list behavior.
  - Test:     `tests/fixtures/profiles/test-fixture/.chat-lms-state/tools.json:1` - current persisted tool shape.
  - External: `https://docs.python.org/3/library/json.html` - JSON object handling and stable machine output.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before production code: `uv run pytest tests/test_agent_tools_registry.py -q` fails because the registry module/default inventory does not exist.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_agent_tools_registry.py tests/test_package_import.py tests/test_repo_privacy.py -q` exits `0`.
  - [ ] `uv run python -c "from chat_lms_agent.agent_tools import default_agent_tools; ids = [tool['id'] for tool in default_agent_tools()]; assert {'side-panel', 'academy-db'} <= set(ids)"` exits `0`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: default registry has required tools
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-1-registry -Command 'uv run python -c "import json; from chat_lms_agent.agent_tools import default_agent_tools; print(json.dumps({''names'': [tool[''name''] for tool in default_agent_tools()]}, sort_keys=True))"' -Evidence evidence/task-1-agent-tools-registry.txt
    Expected: exit_code: 0 and stdout contains side-panel, academy-db, and memory_obligation
    Evidence: evidence/task-1-agent-tools-registry.txt

  Scenario: registry does not create runtime state
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-1-no-state -Command 'Remove-Item -Recurse -Force .tmp-agent-tools-registry -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force .tmp-agent-tools-registry | Out-Null; $env:CHAT_LMS_AGENT_PROFILE_ROOT=(Resolve-Path .tmp-agent-tools-registry).Path; uv run python -c "from pathlib import Path; from chat_lms_agent.agent_tools import default_agent_tools; _ = default_agent_tools(); assert not (Path(''.tmp-agent-tools-registry'') / ''.chat-lms-state'' / ''tools.json'').exists()"' -Evidence evidence/task-1-agent-tools-no-state.txt
    Expected: exit_code: 0 and no `.chat-lms-state/tools.json` is created by reading defaults
    Evidence: evidence/task-1-agent-tools-no-state.txt
  ```

  Commit: YES | Message: `feat(agent-tools): add default registry inventory` | Files: [`src/chat_lms_agent/agent_tools.py`, `tests/test_agent_tools_registry.py`]

- [ ] 2. Proposal validation core

  What to do: Add `src/chat_lms_agent/agent_tool_validation.py` with pure functions that load proposal JSON from a path, validate required fields, aggregate multiple errors, and return structured payloads without printing or exiting. Add fixtures under `tests/fixtures/agent_tools/`, including `valid-tool-proposal.json`, `malformed-missing-memory-command.json`, and a syntactically invalid JSON fixture. RED tests must assert that missing memory and command contracts are reported together as `MISSING_MEMORY_OBLIGATION` and `MISSING_COMMAND_CONTRACT`.
  Must NOT do: Do not mutate profile state during validation; do not stop after the first validation error; do not accept secret-like command text without redaction or error handling.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/tool_handlers.py:133` - current CLI contract errors use `status: ERROR`, `error_code`, and exit `2`.
  - Pattern:  `src/chat_lms_agent/commands.py:73` - invalid argument JSON exits `2`.
  - Pattern:  `src/chat_lms_agent/state.py:127` - JSON load failures are handled without tracebacks.
  - API/Type: `src/chat_lms_agent/state.py:13` - reuse `JsonValue` for JSON-shaped payloads.
  - Test:     `tests/test_harness_contracts.py:16` - parser/CLI errors are asserted by subprocess tests.
  - External: `https://docs.python.org/3/library/argparse.html` - invalid command-line usage conventionally exits `2`.
  - External: `https://docs.python.org/3/library/sys.html#sys.exit` - process exit status semantics.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before production code: `uv run pytest tests/test_agent_tool_validation.py -q` fails on missing validator behavior.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_agent_tool_validation.py tests/test_repo_privacy.py -q` exits `0`.
  - [ ] `uv run python -c "from pathlib import Path; from chat_lms_agent.agent_tool_validation import validate_proposal_file; result = validate_proposal_file(Path('tests/fixtures/agent_tools/malformed-missing-memory-command.json')); assert result.status == 'ERROR'; assert {'MISSING_MEMORY_OBLIGATION', 'MISSING_COMMAND_CONTRACT'} <= set(result.error_codes)"` exits `0`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: valid proposal passes pure validation
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-2-valid-proposal -Command 'uv run python -c "from pathlib import Path; from chat_lms_agent.agent_tool_validation import validate_proposal_file; result = validate_proposal_file(Path(''tests/fixtures/agent_tools/valid-tool-proposal.json'')); assert result.status == ''PASS''; print(result.status)"' -Evidence evidence/task-2-proposal-valid.txt
    Expected: exit_code: 0 and stdout contains PASS
    Evidence: evidence/task-2-proposal-valid.txt

  Scenario: malformed proposal reports both missing contracts
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-2-malformed-proposal -Command 'uv run python -c "from pathlib import Path; from chat_lms_agent.agent_tool_validation import validate_proposal_file; result = validate_proposal_file(Path(''tests/fixtures/agent_tools/malformed-missing-memory-command.json'')); assert ''MISSING_MEMORY_OBLIGATION'' in result.error_codes; assert ''MISSING_COMMAND_CONTRACT'' in result.error_codes; print('',''.join(result.error_codes))"' -Evidence evidence/task-2-proposal-malformed.txt
    Expected: exit_code: 0 and stdout contains both required error codes
    Evidence: evidence/task-2-proposal-malformed.txt
  ```

  Commit: YES | Message: `feat(agent-tools): validate tool proposals` | Files: [`src/chat_lms_agent/agent_tool_validation.py`, `tests/test_agent_tool_validation.py`, `tests/fixtures/agent_tools/*.json`]

- [ ] 3. Memory-obligation core

  What to do: Add a shared memory-obligation checker, preferably `src/chat_lms_agent/memory_obligations.py`, that can compute required memory keys for active tools, registry proposals, and hook payloads. Refactor `session closeout --verify-memory` to use it while preserving existing `missing_memory` output. Add RED tests proving active tools without `tool:<name>` memory still block, active tools with memory pass, and registry-change payloads without memory produce `MEMORY_UPDATE_REQUIRED`.
  Must NOT do: Do not weaken current closeout behavior; do not require memory for inactive/deprecated tools; do not write memory automatically.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [4, 5, 6] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/commands.py:196` - current closeout computes `tool:<name>` obligations for active tools.
  - Pattern:  `src/chat_lms_agent/commands.py:204` - missing memory currently exits `5` with `status: BLOCKED`.
  - Pattern:  `src/chat_lms_agent/state.py:83` - memory entries are loaded from profile state and redacted.
  - Test:     `tests/test_harness_contracts.py:114` - current missing-memory closeout contract.
  - Test:     `tests/test_harness_contracts.py:53` - active tool plus memory should hydrate and remain redacted.
  - External: `https://docs.pytest.org/en/stable/how-to/tmp_path.html` - use isolated temporary profile roots.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before production code: `uv run pytest tests/test_memory_obligations.py -q` fails on missing shared checker behavior.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_memory_obligations.py tests/test_harness_contracts.py -q` exits `0`.
  - [ ] `uv run python -m chat_lms_agent session closeout --verify-memory --profile test-fixture --json` exits `0` and returns `status: PASS`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: closeout passes when active tool memory exists
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-3-closeout-pass -Command "uv run python -m chat_lms_agent session closeout --verify-memory --profile test-fixture --json" -Evidence evidence/task-3-closeout-pass.txt
    Expected: exit_code: 0 and stdout JSON has status PASS with empty missing_memory
    Evidence: evidence/task-3-closeout-pass.txt

  Scenario: registry change without memory is blocked by the core checker
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-3-memory-required -Command 'uv run python -c "from pathlib import Path; from chat_lms_agent.memory_obligations import validate_registry_change_memory; result = validate_registry_change_memory(Path(''tests/fixtures/agent_tools/post-tool-use-registry-change-without-memory.json'')); assert result.error_code == ''MEMORY_UPDATE_REQUIRED''; print(result.error_code)"' -Evidence evidence/task-3-memory-required.txt
    Expected: exit_code: 0 and stdout contains MEMORY_UPDATE_REQUIRED
    Evidence: evidence/task-3-memory-required.txt
  ```

  Commit: YES | Message: `feat(memory): share registry memory obligations` | Files: [`src/chat_lms_agent/memory_obligations.py`, `src/chat_lms_agent/commands.py`, `tests/test_memory_obligations.py`, `tests/fixtures/agent_tools/*.json`]

- [ ] 4. `agent-tools` CLI and hook changed-files integration

  What to do: Extend `src/chat_lms_agent/command_parser.py` with an `agent-tools` namespace containing `list --json` and `validate --from <path> --json`. Add a handler module, preferably `src/chat_lms_agent/agent_tool_handlers.py`, and route it from `src/chat_lms_agent/commands.py`. Extend hook parsing for `--changed-files` and `--memory-updated`, then block managed registry/tool file changes that do not declare a memory update. RED tests must exercise the exact C001 and C002 command lines.
  Must NOT do: Do not break legacy `tool list/show/draft/activate/deprecate`; do not make `agent-tools validate` persist proposals; do not require `--json` to avoid tracebacks.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [F1, F3] | Blocked by: [1, 2, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/command_parser.py:32` - all top-level subcommands are registered centrally.
  - Pattern:  `src/chat_lms_agent/command_parser.py:80` - existing tool namespace shows list/show/draft parser shape.
  - Pattern:  `src/chat_lms_agent/command_parser.py:120` - hook subcommands already include `post-tool-use`.
  - Pattern:  `src/chat_lms_agent/commands.py:53` - dispatcher maps command names to handlers.
  - Pattern:  `src/chat_lms_agent/tool_handlers.py:24` - handler modules receive raw args and repo root.
  - Pattern:  `hooks/hooks.json:4` - registered hooks call `python -m chat_lms_agent hook ... --json`.
  - Test:     `tests/test_harness_contracts.py:158` - registered hook commands must execute.
  - External: `https://docs.python.org/3/library/argparse.html` - subcommands and usage errors.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before production code: `uv run pytest tests/test_tool_registry.py tests/test_harness_memory.py tests/test_hooks.py -q` fails on missing `agent-tools` and hook changed-files behavior.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_agent_tools_cli.py tests/test_hooks.py tests/test_harness_contracts.py tests/test_package_import.py -q` exits `0`.
  - [ ] `uv run python -m chat_lms_agent agent-tools list --json` exits `0`; parsed JSON has `status: PASS` and required names.
  - [ ] `uv run python -m chat_lms_agent agent-tools validate --from tests/fixtures/agent_tools/malformed-missing-memory-command.json --json` exits `2`; parsed JSON includes both required error codes.
  - [ ] `uv run python -m chat_lms_agent hook post-tool-use --changed-files src/chat_lms_agent/agent_tools.py --json` exits nonzero and emits `MEMORY_UPDATE_REQUIRED`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: list required agent tools
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-4-agent-tools-list -Command "uv run python -m chat_lms_agent agent-tools list --json" -Evidence evidence/task-4-agent-tools-list.txt
    Expected: exit_code: 0 and stdout JSON has status PASS with side-panel, academy-db, and memory_obligation
    Evidence: evidence/task-4-agent-tools-list.txt

  Scenario: validate malformed proposal
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-4-agent-tools-validate-error -Command "uv run python -m chat_lms_agent agent-tools validate --from tests/fixtures/agent_tools/malformed-missing-memory-command.json --json" -Evidence evidence/task-4-agent-tools-validate-error.txt
    Expected: exit_code: 2 and stdout JSON includes MISSING_MEMORY_OBLIGATION and MISSING_COMMAND_CONTRACT
    Evidence: evidence/task-4-agent-tools-validate-error.txt

  Scenario: hook changed-files blocks registry change without memory
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-4-hook-memory-required -Command "uv run python -m chat_lms_agent hook post-tool-use --changed-files src/chat_lms_agent/agent_tools.py --json" -Evidence evidence/task-4-hook-memory-required.txt
    Expected: nonzero exit and stdout JSON includes MEMORY_UPDATE_REQUIRED
    Evidence: evidence/task-4-hook-memory-required.txt
  ```

  Commit: YES | Message: `feat(agent-tools): expose registry CLI validation` | Files: [`src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `src/chat_lms_agent/agent_tool_handlers.py`, `tests/test_agent_tools_cli.py`, `tests/test_hooks.py`, `tests/fixtures/agent_tools/*.json`]

- [ ] 5. Context hydration for agent-tool inventory and memory policy

  What to do: Extend `build_codex_context` in `src/chat_lms_agent/context.py` to include three new top-level keys: `agent_tools`, `tool_registry`, and `memory_policy`. `agent_tools` should expose concise default inventory plus active profile tools as needed; `tool_registry` should summarize profile tool counts/statuses without dumping private paths; `memory_policy` should expose obligation rules and unresolved obligations. RED tests must assert the new keys and preserve `side_panel`, `active_tools`, and redaction.
  Must NOT do: Do not dump full profile paths, private state paths, raw secrets, or generated runtime data; do not remove existing `side_panel` payload.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [F1, F3] | Blocked by: [1, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/context.py:23` - current hydration payload shape.
  - Pattern:  `src/chat_lms_agent/context.py:30` - existing `active_tools` and `memory` keys must remain.
  - Pattern:  `src/chat_lms_agent/context.py:32` - existing side-panel contract is included in context.
  - Pattern:  `src/chat_lms_agent/context.py:40` - active profile tools are loaded from state.
  - Pattern:  `src/chat_lms_agent/state.py:105` - redact secret-like values before output.
  - Test:     `tests/test_context_hydration.py:10` - side-panel contract shape in context.
  - Test:     `tests/test_hooks.py:20` - context hydration must redact secrets.
  - Test:     `tests/test_harness_contracts.py:53` - active tools and memory still hydrate.
  - External: `https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html` - subprocess output assertions.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before production code: `uv run pytest tests/test_context_hydration.py tests/test_hooks.py -q` fails on missing `agent_tools`, `tool_registry`, and `memory_policy` assertions added by this task.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_context_hydration.py tests/test_hooks.py tests/test_harness_contracts.py tests/test_side_panel_contract.py -q` exits `0`.
  - [ ] `uv run python -m chat_lms_agent context hydrate --for-codex --profile test-fixture --json` exits `0` and parsed JSON contains `agent_tools`, `tool_registry`, `memory_policy`, `side_panel`, `active_tools`, and `memory`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: context includes registry and memory policy
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-5-context-registry -Command "uv run python -m chat_lms_agent context hydrate --for-codex --profile test-fixture --json" -Evidence evidence/task-5-context-registry.txt
    Expected: exit_code: 0 and stdout JSON includes agent_tools, tool_registry, memory_policy, side_panel, active_tools, and memory
    Evidence: evidence/task-5-context-registry.txt

  Scenario: public repo profile root remains unsafe
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-5-context-unsafe-root -Command "uv run python -m chat_lms_agent context hydrate --for-codex --profile-root . --json" -Evidence evidence/task-5-context-unsafe-root.txt
    Expected: stdout JSON has status UNSAFE and includes PUBLIC_REPO_STATE_REJECTED; no private path is printed
    Evidence: evidence/task-5-context-unsafe-root.txt
  ```

  Commit: YES | Message: `feat(context): hydrate agent tool registry policy` | Files: [`src/chat_lms_agent/context.py`, `tests/test_context_hydration.py`, `tests/test_hooks.py`, `tests/test_harness_contracts.py`]

- [ ] 6. Doctor check for agent tool registry readiness

  What to do: Extend `src/chat_lms_agent/doctor.py` with a pure `agent_tools` check. The `agent_tools` check must call the registry from Task 1 and pass only if required default ids exist and the public registry docs are present. Keep `tool_registry` and `memory_policy` as context hydration fields rather than separate doctor checks. Keep existing path checks and redaction tests green.
  Must NOT do: Do not make doctor create or modify real runtime state; do not repair private profile data; do not leak environment secrets or profile paths.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [F1, F2] | Blocked by: [1, 3]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/doctor.py:29` - existing doctor uses check IDs and path checks.
  - Pattern:  `src/chat_lms_agent/doctor.py:58` - report builder returns aggregate status and exit code.
  - Pattern:  `src/chat_lms_agent/doctor.py:81` - report serializes checks into JSON.
  - Pattern:  `src/chat_lms_agent/commands.py:81` - `doctor --repair --json` emits the doctor report.
  - Test:     `tests/test_doctor.py:10` - doctor JSON contract.
  - Test:     `tests/test_doctor.py:22` - doctor output must not leak secrets.
  - External: `https://docs.pytest.org/en/stable/how-to/monkeypatch.html` - use automatic environment cleanup for redaction tests.

  Acceptance criteria (agent-executable only):
  - [ ] Capture RED evidence before production code: `uv run pytest tests/test_tool_registry.py tests/test_harness_memory.py -q` fails on missing `agent_tools` doctor assertions added by this task.
  - [ ] Capture GREEN evidence after implementation: `uv run pytest tests/test_tool_registry.py tests/test_harness_memory.py tests/test_repo_privacy.py -q` exits `0`.
  - [ ] `uv run python -m chat_lms_agent doctor --repair --json` exits `0`, parsed JSON `checks[*].id` contains `agent_tools`, and the `agent_tools` check status is `PASS`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: doctor reports agent tool checks
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-6-doctor-agent-tools -Command "uv run python -m chat_lms_agent doctor --repair --json" -Evidence evidence/task-6-doctor-agent-tools.txt
    Expected: exit_code: 0 and stdout JSON checks include agent_tools PASS
    Evidence: evidence/task-6-doctor-agent-tools.txt

  Scenario: doctor redacts private-like environment values
    Tool:     PowerShell CLI capture
    Steps:    powershell -ExecutionPolicy Bypass -File scripts/qa/capture-command.ps1 -Name task-6-doctor-redaction -Command '$env:PRIVATE_SAMPLE_VALUE="private-value-that-must-not-leak"; uv run python -m chat_lms_agent doctor --repair --json' -Evidence evidence/task-6-doctor-redaction.txt
    Expected: exit_code: 0 and evidence does not contain private-value-that-must-not-leak
    Evidence: evidence/task-6-doctor-redaction.txt
  ```

  Commit: YES | Message: `feat(doctor): verify agent tool harness health` | Files: [`src/chat_lms_agent/doctor.py`, `tests/test_doctor.py`]

## Final verification wave (MANDATORY - after all implementation tasks)
> Runs in PARALLEL. ALL must APPROVE. Surface results to the caller and wait for an explicit "okay" before declaring complete.
- [ ] F1. Plan compliance audit - every task done, every acceptance criterion met
- [ ] F2. Code quality review - diagnostics clean, idioms match, no dead code
- [ ] F3. Real manual QA - every QA scenario executed with evidence captured
- [ ] F4. Scope fidelity - nothing extra shipped beyond Must-Have, nothing Must-NOT-Have introduced

## Commit strategy
- One logical change per commit. Conventional Commits (`<type>(<scope>): <subject>` body + footer).
- Atomic: every commit builds and passes tests on its own.
- No "WIP" / "fix typo squash later" commits on the final branch - clean up before merge.
- Reference the plan file path in the final commit footer: `Plan: plans/harness-strengthening-implementation.md`.

## Success criteria
- All Must-Have shipped; all QA scenarios pass with captured evidence; F1-F4 approved; commit history clean.
