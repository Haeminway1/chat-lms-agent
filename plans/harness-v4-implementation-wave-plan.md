# Harness V4 Implementation Wave Plan

## TL;DR
> Summary:      Implement the existing V4 harness plan test-first while keeping Codex Desktop as the current host and preserving transition-ready core contracts for future desktop or Web SaaS adapters.
> Deliverables:
> - Source-pinned OSS registry and repaired public docs truth.
> - Reuse-before-build gate, skill validation, context map, reversible offload, trace inspector, layered memory, approval risk, goal verification, host-adapter contract, and optional read-only MCP discovery.
> - Automated tests and tmux-captured CLI QA transcripts for every task.
> Effort:       Large
> Risk:         Medium - broad cross-module surface with strict public/private data boundaries.

## Scope
### Must have
- Preserve Codex Desktop as the current app harness host; future `standalone_desktop` and `web_saas` remain host-adapter contracts, not implemented runtimes.
- Treat `plans/harness-v4-oss-reference-expansion-plan.md` as the upstream V4 product plan. It is currently untracked; the executor must include it deliberately in commit scope or explicitly leave it untouched.
- Add tests before implementation for every task.
- Keep runtime data under private profile state, never in the public repo. Existing state boundary is `.chat-lms-state` in `src/chat_lms_agent/state.py:15`.
- Use current CLI routing through `src/chat_lms_agent/commands.py:71` and parser registration through `src/chat_lms_agent/command_parser.py:29`.
- Keep trace/audit canonical writes as per-record JSON, with JSONL compatibility read/import/export only, matching `src/chat_lms_agent/journal.py:44` and `src/chat_lms_agent/journal.py:160`.
- Validate all public outputs for redaction of private paths, secrets, raw learner-like data, and local machine paths.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- No real learner data, private reports, saved secrets, local absolute paths, or external account state in committed files.
- No replacement LLM loop, provider router, subagent process manager, graph runtime, or default cloud memory.
- No default proxy/wrapper around Codex Desktop or model traffic.
- No write-capable MCP proxy; MCP is optional, disabled by default, read-only, stdio-first.
- No copying external OSS source without source-pinned license review and explicit direct-use decision.
- No manually edited context maps/offload summaries as truth; generated views must point back to canonical sources.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD + pytest, subprocess CLI contract tests, docs contract tests, and privacy tests.
- QA policy: every task has agent-executed scenarios, including tmux-captured CLI smoke/failure cases.
- Evidence: `evidence/task-<N>-<slug>.<ext>`

## Execution strategy
### Parallel execution waves
> Target 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks to maximize parallelism.

Wave 1 (no dependencies):
- Task 1: Repair docs truth and add OSS source registry.
- Task 2: Add V4 state/redaction/retention foundation.
- Task 3: Define host-adapter contract and durable workflow gate.
- Task 4: Add skill discovery and validation commands.
- Task 5: Add approval risk taxonomy foundation.

Wave 2 (after Wave 1):
- Task 6: depends [1] - Add reuse-before-build gate.
- Task 7: depends [1, 2, 3, 4] - Add context map build/show and hydration link.
- Task 8: depends [2, 5] - Add trajectory trace export/inspect.
- Task 9: depends [2, 7] - Harden layered memory taxonomy and hydration.

Wave 3 (after Wave 2):
- Task 10: depends [2, 7, 9] - Add reversible context offload and budget.
- Task 11: depends [5, 8, 9, 10] - Add verifier-gated goal runtime.
- Task 12: depends [1, 3, 4, 7, 8, 9, 10] - Add optional read-only MCP discovery adapter.

Critical path: Task 1 -> Task 7 -> Task 10 -> Task 11 -> Task 12

### Dependency matrix
| Task | Depends on | Blocks | Can parallelize with |
|------|------------|--------|----------------------|
| 1    | none       | 6, 7, 12 | 2, 3, 4, 5 |
| 2    | none       | 7, 8, 9, 10 | 1, 3, 4, 5 |
| 3    | none       | 7, 12 | 1, 2, 4, 5 |
| 4    | none       | 7, 12 | 1, 2, 3, 5 |
| 5    | none       | 8, 11 | 1, 2, 3, 4 |
| 6    | 1          | none | 7, 8, 9 |
| 7    | 1, 2, 3, 4 | 9, 10, 12 | 6, 8 |
| 8    | 2, 5       | 11, 12 | 6, 7, 9 |
| 9    | 2, 7       | 10, 11, 12 | 6, 8 |
| 10   | 2, 7, 9    | 11, 12 | none |
| 11   | 5, 8, 9, 10 | none | 12 only after dependency completion |
| 12   | 1, 3, 4, 7, 8, 9, 10 | none | 11 only after dependency completion |

## Todos
> Implementation + Test = ONE task. Never separate.
> Every task MUST have: References + Acceptance Criteria + QA Scenarios + Commit.

- [ ] 1. Repair docs truth and add OSS source registry

  What to do: Start by rewriting failing docs tests for the corrected side-panel terminology, no mojibake, and a new `docs/oss-reference-registry.md` schema. Add the registry with all V4 references, pinned SHAs where provided, observed date `2026-06-09`, adoption status, local mapping, privacy boundary, freshness note, and must-not-copy rule. Convert `docs/golden-standards.md` into a summary that points to the registry. Align `docs/runtime-boundary.md` with per-record JSON trace/audit storage, JSONL compatibility, retention defaults, and lock expectations.
  Must NOT do: Do not preserve corrupted text as expected output. Do not make `docs/golden-standards.md` a second source of truth. Do not add real private examples.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [6, 7, 12] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `tests/test_docs_contract.py:6` - existing docs contract tests; these currently lock corrupted terminology and must be flipped test-first.
  - Pattern:  `docs/terminology.md:3` - current side-panel terminology contains mojibake that V4 explicitly repairs.
  - Pattern:  `docs/golden-standards.md:1` - current reference summary to demote behind the registry SSoT.
  - Pattern:  `docs/runtime-boundary.md:18` - public/private boundary language to preserve and expand.
  - Pattern:  `src/chat_lms_agent/journal.py:44` - trace/audit writes are per-record JSON.
  - Pattern:  `src/chat_lms_agent/journal.py:160` - trace/audit reads include `.json` and `.jsonl` compatibility.
  - Test:     `tests/test_repo_privacy.py:45` - public repo privacy scanner to keep green and extend if new docs need forbidden-term coverage.
  - External: `https://developers.openai.com/codex/guides/agents-md` - Codex reads and layers `AGENTS.md` project guidance.
  - External: `https://developers.openai.com/codex/app` - Codex app is the current desktop command center with app/worktree/thread surfaces.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_docs_contract.py tests/test_repo_privacy.py -q` exits 0.
  - [ ] `Select-String -Path docs\*.md -Pattern '蹂댁|媛|�|\?⑤꼸|\?쒖'` returns no corrupted canonical names.
  - [ ] A Python docs-schema test asserts every registry entry has `id`, `source_url`, `pinned_head_sha`, `observed_at`, `license`, `popularity_signal`, `local_problem_matched`, `adoption_status`, `local_mapping`, `must_not_copy`, `privacy_boundary`, and `freshness_note`.
  - [ ] `docs/golden-standards.md` links to `docs/oss-reference-registry.md` and contains no divergent adoption decision table.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: registry and docs contracts pass
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task1_docs "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-1-docs -Command 'uv run pytest tests/test_docs_contract.py tests/test_repo_privacy.py -q' -Evidence evidence/task-1-docs.txt"
    Expected: evidence/task-1-docs.txt contains exit_code: 0 and pytest reports all selected tests passed.
    Evidence: evidence/task-1-docs.txt

  Scenario: corrupted canonical terminology is rejected
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task1_mojibake "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-1-mojibake -Command 'Select-String -Path docs\*.md -Pattern ''蹂댁|媛|�|\?⑤꼸|\?쒖''; if ($LASTEXITCODE -eq 0) { exit 1 } else { exit 0 }' -Evidence evidence/task-1-docs-error.txt"
    Expected: evidence/task-1-docs-error.txt contains exit_code: 0 because no corrupted canonical text is found.
    Evidence: evidence/task-1-docs-error.txt
  ```

  Commit: YES | Message: `docs(v4): add oss reference registry` | Files: [`docs/oss-reference-registry.md`, `docs/golden-standards.md`, `docs/terminology.md`, `docs/runtime-boundary.md`, `tests/test_docs_contract.py`, `tests/test_repo_privacy.py`, `plans/harness-v4-oss-reference-expansion-plan.md` if intentionally committed]

- [ ] 2. Add V4 state/redaction/retention foundation

  What to do: Add tests first for reusable profile-state helpers needed by context maps, offloads, goals, and retention metadata. Extend state utilities with safe generated-view directories, JSON read/write helpers, content hashing, redacted public payload helpers, and retention/lock metadata constants. Keep writes atomic and outside the repo unless using synthetic test fixtures.
  Must NOT do: Do not move existing `tools.json` or `memory.json` storage without a migration plan. Do not write profile state into the public repo.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [7, 8, 9, 10] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - API/Type: `src/chat_lms_agent/state.py:15` - existing private state directory name.
  - API/Type: `src/chat_lms_agent/state.py:41` - profile root resolver rejects public repo state.
  - Pattern:  `src/chat_lms_agent/state.py:108` - existing secret redaction helper.
  - Pattern:  `src/chat_lms_agent/state.py:148` - existing atomic JSON write style.
  - Pattern:  `src/chat_lms_agent/journal.py:118` - profile/repo path redaction behavior.
  - Test:     `tests/test_repo_privacy.py:82` - ignored local artifacts must remain covered.
  - External: `https://docs.pytest.org/en/stable/builtin.html` - `tmp_path` provides unique temporary directories and `monkeypatch` changes are undone after test completion.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_state_v4.py tests/test_repo_privacy.py -q` exits 0.
  - [ ] New state helpers return `PUBLIC_REPO_STATE_REJECTED` for repo-root profile paths.
  - [ ] Synthetic secret/path payloads are redacted in public JSON output and exact originals remain private where required.
  - [ ] Retention defaults are exposed as machine-readable JSON in the relevant context/doctor payloads.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: state helpers reject public repo profile root
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task2_state "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-2-state -Command 'uv run pytest tests/test_state_v4.py -q' -Evidence evidence/task-2-state.txt"
    Expected: evidence/task-2-state.txt contains exit_code: 0 and tests confirm repo-root profile paths are unsafe.
    Evidence: evidence/task-2-state.txt

  Scenario: direct CLI profile inspect rejects repo root
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task2_profile_error "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-2-profile-error -Command 'python -m chat_lms_agent profile inspect --profile-root . --json; if ($LASTEXITCODE -eq 4) { exit 0 } else { exit 1 }' -Evidence evidence/task-2-state-error.txt"
    Expected: evidence/task-2-state-error.txt contains exit_code: 0 and command output includes PUBLIC_REPO_STATE_REJECTED.
    Evidence: evidence/task-2-state-error.txt
  ```

  Commit: YES | Message: `feat(state): add v4 profile state foundation` | Files: [`src/chat_lms_agent/state.py`, `src/chat_lms_agent/journal.py`, `src/chat_lms_agent/doctor.py`, `tests/test_state_v4.py`, affected docs]

- [ ] 3. Define host-adapter contract and durable workflow gate

  What to do: Add tests first for a host-neutral `HostAdapter` contract document and JSON context payload. Extend harness context so `codex_desktop` is current, `standalone_desktop` and `web_saas` are future adapters, and durable workflow adoption remains a documented decision gate. Keep this contract as docs/types/tests, not a new runtime.
  Must NOT do: Do not import Codex hook payload details into core storage schemas. Do not implement standalone desktop/Web SaaS, queues, workers, or graph orchestration.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [7, 12] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - API/Type: `src/chat_lms_agent/harness_events.py:35` - current harness context already names current and future hosts.
  - API/Type: `src/chat_lms_agent/harness_events.py:16` - event normalization contract.
  - Pattern:  `src/chat_lms_agent/commands.py:85` - `harness` command dispatch.
  - Pattern:  `src/chat_lms_agent/v3_command_parser.py:20` - `harness event normalize` parser.
  - Test:     `tests/test_harness_contracts.py` - existing harness contract coverage anchor.
  - External: `https://developers.openai.com/codex/app` - Codex app is the current local desktop surface.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_harness_contracts.py tests/test_host_adapter_contract.py -q` exits 0.
  - [ ] `python -m chat_lms_agent context hydrate --for-codex --json` includes current host and future host adapters without enabling them.
  - [ ] Durable workflow gate requires at least two explicit future conditions before recommending LangGraph/Temporal/etc.
  - [ ] No new runtime dependency is added to `[project].dependencies` in `pyproject.toml`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: host adapter context is visible in hydration
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task3_host "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-3-host -Command 'uv run pytest tests/test_host_adapter_contract.py -q; python -m chat_lms_agent context hydrate --for-codex --json' -Evidence evidence/task-3-host.txt"
    Expected: evidence/task-3-host.txt contains exit_code: 0 and JSON includes codex_desktop, standalone_desktop, and web_saas.
    Evidence: evidence/task-3-host.txt

  Scenario: invalid host event is rejected cleanly
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task3_invalid_event "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-3-invalid-event -Command '$p=Join-Path $env:TEMP ''bad-harness-event.json''; Set-Content -Path $p -Value ''not-json''; python -m chat_lms_agent harness event normalize --from $p --json; if ($LASTEXITCODE -eq 2) { exit 0 } else { exit 1 }' -Evidence evidence/task-3-host-error.txt"
    Expected: evidence/task-3-host-error.txt contains exit_code: 0 and output includes INVALID_HARNESS_EVENT_PAYLOAD.
    Evidence: evidence/task-3-host-error.txt
  ```

  Commit: YES | Message: `feat(harness): define host adapter contract` | Files: [`src/chat_lms_agent/harness_events.py`, `src/chat_lms_agent/harness_handlers.py`, `docs/runtime-boundary.md`, `tests/test_host_adapter_contract.py`, `tests/test_harness_contracts.py`]

- [ ] 4. Add skill discovery and validation commands

  What to do: Add tests first for `python -m chat_lms_agent skills list --json` and `python -m chat_lms_agent skills validate --json`. Implement a small skills module and CLI handler that discovers `.agents/skills/*/SKILL.md`, validates required frontmatter `name` and `description`, checks optional `scripts/`, `references/`, `assets/`, rejects private data, and flags oversized always-loaded skill content. Include skill validation in `doctor`.
  Must NOT do: Do not execute skill scripts during validation. Do not add private profile data or giant reference dumps to skills.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [7, 12] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `tests/test_skills.py:5` - existing required local skills.
  - Pattern:  `.agents/skills/chat-lms-onboarding/SKILL.md` - existing skill file to validate.
  - Pattern:  `src/chat_lms_agent/command_parser.py:29` - parser registration style.
  - Pattern:  `src/chat_lms_agent/commands.py:71` - CLI dispatch table.
  - Pattern:  `src/chat_lms_agent/doctor.py:37` - doctor required-path checks include skills today.
  - External: `https://developers.openai.com/codex/skills` - skills are reusable workflows with required `SKILL.md` metadata and optional `scripts/`, `references/`, `assets/`; Codex loads full instructions only when selected.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_skills.py tests/test_skills_cli_v4.py -q` exits 0.
  - [ ] `python -m chat_lms_agent skills list --json` returns both required skills with name, description, path, and trigger summary.
  - [ ] `python -m chat_lms_agent skills validate --json` exits 0 for current skills and exits 2 for malformed synthetic skills.
  - [ ] `python -m chat_lms_agent doctor --json` includes a `skills` or `skills_validate` check.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: skills list and validate pass
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task4_skills "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-4-skills -Command 'uv run pytest tests/test_skills.py tests/test_skills_cli_v4.py -q; python -m chat_lms_agent skills list --json; python -m chat_lms_agent skills validate --json' -Evidence evidence/task-4-skills.txt"
    Expected: evidence/task-4-skills.txt contains exit_code: 0 and outputs include chat-lms-onboarding and chat-lms-qa.
    Evidence: evidence/task-4-skills.txt

  Scenario: malformed skill fails validation
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task4_bad_skill "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-4-bad-skill -Command '$d=Join-Path $env:TEMP ''bad-chat-lms-skill''; New-Item -ItemType Directory -Force -Path $d | Out-Null; Set-Content -Path (Join-Path $d ''SKILL.md'') -Value ''# missing frontmatter''; python -m chat_lms_agent skills validate --root $d --json; if ($LASTEXITCODE -eq 2) { exit 0 } else { exit 1 }' -Evidence evidence/task-4-skills-error.txt"
    Expected: evidence/task-4-skills-error.txt contains exit_code: 0 and output includes MISSING_SKILL_FRONTMATTER or equivalent exact error.
    Evidence: evidence/task-4-skills-error.txt
  ```

  Commit: YES | Message: `feat(skills): validate reusable workflow drawers` | Files: [`src/chat_lms_agent/skills.py`, `src/chat_lms_agent/skills_handlers.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `src/chat_lms_agent/doctor.py`, `tests/test_skills.py`, `tests/test_skills_cli_v4.py`]

- [ ] 5. Add approval risk taxonomy foundation

  What to do: Add tests first for risk classes and schema-versioned approval compatibility. Extend approval records with risk class, reason, diff/plan summary, rollback note, expiry, and trace link while preserving existing V3 records. Enforce self-approval rejection, terminal consumed/denied behavior, expired approval rejection, wrong-actor rejection where actor is specified, and low-risk non-blocking behavior for read-only/draft-only classes.
  Must NOT do: Do not make approval a vague checkbox. Do not require human approval for read-only commands. Do not break existing approval records.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [8, 11] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - API/Type: `src/chat_lms_agent/approvals.py:13` - existing approval schema constants.
  - Pattern:  `src/chat_lms_agent/approvals.py:29` - current approval request creation.
  - Pattern:  `src/chat_lms_agent/approvals.py:55` - self-approval rejection.
  - Pattern:  `src/chat_lms_agent/approvals.py:119` - approval status helpers.
  - Pattern:  `src/chat_lms_agent/approvals.py:206` - terminal consumed/denied errors.
  - Test:     `tests/test_trace_audit_approval.py:20` - existing approval lifecycle/redaction test.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_trace_audit_approval.py tests/test_approval_risk_v4.py -q` exits 0.
  - [ ] Existing V3 approval fixtures remain readable as schema-compatible `approval-v1` records.
  - [ ] New tests cover denied, expired, reused/consumed, self-approved, and wrong-actor approval cases.
  - [ ] Risk mapping blocks private data writes, external writes, canonical writes, and destructive operations unless approved.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: approval risk lifecycle passes
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task5_approval "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-5-approval -Command 'uv run pytest tests/test_trace_audit_approval.py tests/test_approval_risk_v4.py -q' -Evidence evidence/task-5-approval.txt"
    Expected: evidence/task-5-approval.txt contains exit_code: 0 and pytest reports all selected tests passed.
    Evidence: evidence/task-5-approval.txt

  Scenario: agent self-approval stays rejected
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task5_self_approval "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-5-self-approval -Command 'uv run pytest tests/test_approval_risk_v4.py -q -k self_approval' -Evidence evidence/task-5-approval-error.txt"
    Expected: evidence/task-5-approval-error.txt contains exit_code: 0 and test output references SELF_APPROVAL_REJECTED.
    Evidence: evidence/task-5-approval-error.txt
  ```

  Commit: YES | Message: `feat(approval): add risk taxonomy` | Files: [`src/chat_lms_agent/approvals.py`, `src/chat_lms_agent/approval_handlers.py`, `src/chat_lms_agent/doctor.py`, `tests/test_approval_risk_v4.py`, `tests/test_trace_audit_approval.py`]

- [ ] 6. Add reuse-before-build gate

  What to do: Add tests first for a required `reuse_review` object on agent-tool proposals and a new `agent-tools reuse-check --intent <text> --json` public command. Search existing Chat LMS tools, skills, side-panel blocks, docs, and registry entries. Validation must reject proposals missing reuse review, but keep small reversible work flexible through explicit `custom_build_justified`.
  Must NOT do: Do not block low-risk one-off investigation. Do not scaffold/register a reusable tool without a reuse review.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [] | Blocked by: [1]

  References (executor has NO interview context - be exhaustive):
  - API/Type: `src/chat_lms_agent/agent_tools.py:32` - existing tool typed shape.
  - Pattern:  `src/chat_lms_agent/agent_tools.py:60` - default public tool registry.
  - Pattern:  `src/chat_lms_agent/agent_tools.py:146` - current proposal validator to extend.
  - Pattern:  `src/chat_lms_agent/agent_tool_lifecycle.py:14` - lifecycle-required proposal contracts.
  - Pattern:  `src/chat_lms_agent/agent_tool_handlers.py:23` - handler already splits public vs profile-backed commands.
  - Pattern:  `src/chat_lms_agent/command_parser.py:105` - `agent-tools` parser location.
  - Test:     `tests/test_tool_registry.py:25` - existing proposal validation test.
  - Test:     `tests/test_agent_tools_lifecycle_cli.py:63` - scaffold validation coverage.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_tool_registry.py tests/test_agent_tools_lifecycle_cli.py tests/test_agent_tools_reuse_v4.py -q` exits 0.
  - [ ] `agent-tools validate` rejects missing `reuse_review` with `MISSING_REUSE_REVIEW`.
  - [ ] `agent-tools reuse-check --intent "build side panel report" --json` returns existing side-panel candidates.
  - [ ] `agent-tools reuse-check --intent "new synthetic calendar adapter" --json` can return `custom_build_justified` only with checked candidates listed.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: reuse-check finds existing side-panel tool
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task6_reuse "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-6-reuse -Command 'uv run pytest tests/test_agent_tools_reuse_v4.py -q; python -m chat_lms_agent agent-tools reuse-check --intent ''build side panel report'' --json' -Evidence evidence/task-6-reuse.txt"
    Expected: evidence/task-6-reuse.txt contains exit_code: 0 and output includes side-panel as an existing candidate.
    Evidence: evidence/task-6-reuse.txt

  Scenario: missing reuse review proposal fails validation
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task6_missing_reuse "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-6-missing-reuse -Command '$p=Join-Path $env:TEMP ''missing-reuse-tool.json''; Set-Content -Path $p -Value ''{\"id\":\"x\",\"summary\":\"x\",\"command_contract\":{\"commands\":[\"echo x\"]},\"memory_obligation\":\"x\"}''; python -m chat_lms_agent agent-tools validate --from $p --json; if ($LASTEXITCODE -eq 2) { exit 0 } else { exit 1 }' -Evidence evidence/task-6-reuse-error.txt"
    Expected: evidence/task-6-reuse-error.txt contains exit_code: 0 and output includes MISSING_REUSE_REVIEW.
    Evidence: evidence/task-6-reuse-error.txt
  ```

  Commit: YES | Message: `feat(agent-tools): require reuse review` | Files: [`src/chat_lms_agent/agent_tools.py`, `src/chat_lms_agent/agent_tool_lifecycle.py`, `src/chat_lms_agent/agent_tool_handlers.py`, `src/chat_lms_agent/command_parser.py`, `docs/agent-tool-registry.md`, `tests/test_agent_tools_reuse_v4.py`, existing agent-tool tests]

- [ ] 7. Add context map build/show and hydration link

  What to do: Add tests first for `context map build` and `context map show`. Build a generated, stale-detectable map from canonical docs, CLI registry, skills, side-panel catalog, trace/audit indexes, memory summaries, academy DB schema/query names, and host-adapter contract. Store generated map under private profile state. Hydration may include compact map metadata and warnings, but the map never becomes truth.
  Must NOT do: Do not store raw private data in the map. Do not require manual map editing. Do not make stale maps pass silently.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [9, 10, 12] | Blocked by: [1, 2, 3, 4]

  References (executor has NO interview context - be exhaustive):
  - API/Type: `src/chat_lms_agent/context.py:31` - existing context hydration payload builder.
  - Pattern:  `src/chat_lms_agent/context.py:36` - context includes side panel, harness, trace, audit, approvals, agent tools, memory policy, and academy DB.
  - Pattern:  `src/chat_lms_agent/context.py:64` - active private tools and memory are redacted into context.
  - Pattern:  `src/chat_lms_agent/command_parser.py:60` - current `context hydrate` parser.
  - Test:     `tests/test_context_hydration.py:10` - existing context hydration test style.
  - Test:     `tests/test_tool_registry.py:56` - context hydration already includes tool registry.
  - External: `https://developers.openai.com/codex/app` - Codex app supports plans, sources, task summaries, and artifacts in the sidebar; Chat LMS context map should remain a local generated view.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_context_hydration.py tests/test_context_map_v4.py -q` exits 0.
  - [ ] `python -m chat_lms_agent context map build --profile-root <tmp> --json` writes a generated map with source hashes/freshness metadata.
  - [ ] `context map show` returns redacted summaries and flags stale maps when canonical source changes.
  - [ ] `context hydrate --for-codex --profile-root <tmp> --json` includes compact `context_map` metadata without raw private data.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: context map build/show works
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task7_map "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-7-map -Command '$p=Join-Path $env:TEMP ''chat-lms-v4-map''; python -m chat_lms_agent context map build --profile-root $p --json; python -m chat_lms_agent context map show --profile-root $p --json; uv run pytest tests/test_context_map_v4.py -q' -Evidence evidence/task-7-context-map.txt"
    Expected: evidence/task-7-context-map.txt contains exit_code: 0 and output includes context_map with generated_from sources.
    Evidence: evidence/task-7-context-map.txt

  Scenario: stale or missing map is recoverable
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task7_stale "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-7-stale-map -Command 'uv run pytest tests/test_context_map_v4.py -q -k stale' -Evidence evidence/task-7-context-map-error.txt"
    Expected: evidence/task-7-context-map-error.txt contains exit_code: 0 and tests assert STALE_CONTEXT_MAP or equivalent exact warning.
    Evidence: evidence/task-7-context-map-error.txt
  ```

  Commit: YES | Message: `feat(context): add generated context map` | Files: [`src/chat_lms_agent/context_map.py`, `src/chat_lms_agent/context_handlers.py` if created, `src/chat_lms_agent/context.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `tests/test_context_map_v4.py`, existing context tests]

- [ ] 8. Add trajectory trace export/inspect

  What to do: Add tests first for `trace export --format trajectory --json` and `trace inspect --id <trace-id> --json`. Read from current per-record JSON and compatible JSONL traces/audits. Produce redacted causal views with user intent, command/tool, result status, approval checkpoint, memory/audit effects, and next-session obligations where available.
  Must NOT do: Do not create a second canonical trace ledger. Do not require hand-opening raw JSONL. Do not leak private paths or raw stdout.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [11, 12] | Blocked by: [2, 5]

  References (executor has NO interview context - be exhaustive):
  - API/Type: `src/chat_lms_agent/journal.py:15` - trace/audit schema versions.
  - Pattern:  `src/chat_lms_agent/journal.py:86` - trace list payload shape.
  - Pattern:  `src/chat_lms_agent/journal.py:96` - trace show behavior.
  - Pattern:  `src/chat_lms_agent/journal.py:174` - record reads from `.json` and `.jsonl`.
  - Pattern:  `src/chat_lms_agent/trace_audit_handlers.py:12` - current trace CLI handler.
  - Pattern:  `src/chat_lms_agent/v3_command_parser.py:43` - current trace parser only has `list` and `show`.
  - Test:     `tests/test_memory_session_v3.py:112` - session summary reads JSONL trace/audit refs without private paths.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_trace_audit_approval.py tests/test_trace_trajectory_v4.py -q` exits 0.
  - [ ] `trace export --format trajectory --profile-root <tmp> --json` returns ordered redacted trajectory entries.
  - [ ] `trace inspect --id <id> --profile-root <tmp> --json` returns trace plus related audit/approval refs.
  - [ ] Missing trace id exits 2 with `TRACE_NOT_FOUND`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: trajectory export reads JSON and JSONL
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task8_trace "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-8-trace -Command 'uv run pytest tests/test_trace_trajectory_v4.py -q; $p=Join-Path $env:TEMP ''chat-lms-v4-trace''; python -m chat_lms_agent trace export --profile-root $p --format trajectory --json' -Evidence evidence/task-8-trace.txt"
    Expected: evidence/task-8-trace.txt contains exit_code: 0 and output includes schema_version trajectory or an empty PASS trajectory for a clean profile.
    Evidence: evidence/task-8-trace.txt

  Scenario: missing trace inspect returns exact error
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task8_trace_missing "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-8-trace-missing -Command '$p=Join-Path $env:TEMP ''chat-lms-v4-trace-missing''; python -m chat_lms_agent trace inspect --profile-root $p --id missing-trace --json; if ($LASTEXITCODE -eq 2) { exit 0 } else { exit 1 }' -Evidence evidence/task-8-trace-error.txt"
    Expected: evidence/task-8-trace-error.txt contains exit_code: 0 and output includes TRACE_NOT_FOUND.
    Evidence: evidence/task-8-trace-error.txt
  ```

  Commit: YES | Message: `feat(trace): export trajectory views` | Files: [`src/chat_lms_agent/journal.py`, `src/chat_lms_agent/trace_audit_handlers.py`, `src/chat_lms_agent/v3_command_parser.py`, `tests/test_trace_trajectory_v4.py`, existing trace tests]

- [ ] 9. Harden layered memory taxonomy and hydration

  What to do: Add tests first for memory levels/categories, temporal fields, draft-first canonical changes, add-only defaults, historical-vs-current resolution, and drill-down pointers to `conversation_ref`, `offload_id`, or source refs. Extend memory payload parsing and CLI draft/apply/list/compact so L0 raw refs are not hydratable by default, L1/L2/L3 have explicit hydration rules, and persona/policy/current canonical changes require review.
  Must NOT do: Do not require embeddings/vector DB/cloud memory. Do not silently overwrite canonical memory. Do not inject raw history into default hydration.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [10, 11, 12] | Blocked by: [2, 7]

  References (executor has NO interview context - be exhaustive):
  - API/Type: `src/chat_lms_agent/state.py:29` - current minimal memory payload.
  - Pattern:  `src/chat_lms_agent/memory_handlers.py:34` - current memory CLI routes.
  - Pattern:  `src/chat_lms_agent/memory_handlers.py:61` - current upsert behavior.
  - Pattern:  `src/chat_lms_agent/memory_handlers.py:75` - current compact summary.
  - Pattern:  `src/chat_lms_agent/memory_handlers.py:166` - current draft apply behavior.
  - Pattern:  `src/chat_lms_agent/context.py:83` - current memory hydration payload.
  - Test:     `tests/test_memory_session_v3.py:10` - existing compact/session memory behavior.
  - Test:     `tests/test_memory_drafts.py` - draft/apply behavior anchor.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_memory*.py tests/test_context_hydration.py tests/test_memory_layers_v4.py -q` exits 0.
  - [ ] Memory `list --json` exposes level/category/current/temporal metadata without raw private source text.
  - [ ] `memory apply-draft` rejects canonical persona/policy changes without required review metadata.
  - [ ] `context hydrate` includes current tool knowledge and academy policy, excludes raw L0 refs, and marks historical facts.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: layered memory hydration works
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task9_memory "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-9-memory -Command 'uv run pytest tests/test_memory_layers_v4.py tests/test_memory_session_v3.py -q' -Evidence evidence/task-9-memory.txt"
    Expected: evidence/task-9-memory.txt contains exit_code: 0 and tests prove L0 refs are not hydrated by default.
    Evidence: evidence/task-9-memory.txt

  Scenario: unreviewed canonical persona or policy memory is rejected
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task9_memory_review "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-9-memory-review -Command 'uv run pytest tests/test_memory_layers_v4.py -q -k review_required' -Evidence evidence/task-9-memory-error.txt"
    Expected: evidence/task-9-memory-error.txt contains exit_code: 0 and tests assert MEMORY_REVIEW_REQUIRED or equivalent exact error.
    Evidence: evidence/task-9-memory-error.txt
  ```

  Commit: YES | Message: `feat(memory): add layered taxonomy` | Files: [`src/chat_lms_agent/state.py`, `src/chat_lms_agent/memory_handlers.py`, `src/chat_lms_agent/context.py`, `src/chat_lms_agent/memory_obligations.py`, `tests/test_memory_layers_v4.py`, existing memory/context tests]

- [ ] 10. Add reversible context offload and budget

  What to do: Add tests first for `context offload put/get` and `context budget show`. Store exact originals in private profile state with content hash, kind, source path redaction, generated summary, and retrieval metadata. Hydration may include compact summaries plus `offload_id`, never raw content. Missing originals must be recoverable integrity errors. Compression benchmarks, if added, must require regression parity as well as token savings.
  Must NOT do: Do not add Headroom as a default dependency. Do not delete or mutate originals. Do not route model/API traffic through any proxy/wrapper.

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [11, 12] | Blocked by: [2, 7, 9]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/context.py:31` - hydration point for compact offload summaries.
  - Pattern:  `src/chat_lms_agent/state.py:148` - atomic private JSON write style.
  - Pattern:  `src/chat_lms_agent/journal.py:118` - runtime path and raw stdout redaction.
  - Pattern:  `src/chat_lms_agent/command_parser.py:60` - extend context parser with `offload` and `budget`.
  - Test:     `tests/test_context_hydration.py:10` - existing context contract style.
  - External: `https://docs.pytest.org/en/stable/builtin.html` - use `tmp_path` for synthetic large-output fixtures without repo pollution.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_context_offload_v4.py tests/test_context_hydration.py tests/test_repo_privacy.py -q` exits 0.
  - [ ] `context offload put --from <synthetic-file>` stores exact original under private state and returns `offload_id` and hash.
  - [ ] `context offload get --ref <offload-id>` retrieves exact original and verifies hash.
  - [ ] `context budget show` reports summary/original counts and token/byte estimates without raw private data.
  - [ ] Missing original returns a recoverable integrity error with nonzero exit.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: synthetic output offload round-trips exactly
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task10_offload "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-10-offload -Command '$p=Join-Path $env:TEMP ''chat-lms-v4-offload''; $f=Join-Path $env:TEMP ''large-output.txt''; Set-Content -Path $f -Value ((1..200) -join '' synthetic line ''); python -m chat_lms_agent context offload put --profile-root $p --kind tool_output --from $f --json; python -m chat_lms_agent context budget show --profile-root $p --json; uv run pytest tests/test_context_offload_v4.py -q' -Evidence evidence/task-10-offload.txt"
    Expected: evidence/task-10-offload.txt contains exit_code: 0 and output includes offload_id, content_hash, and budget totals.
    Evidence: evidence/task-10-offload.txt

  Scenario: missing offload original is recoverable integrity error
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task10_missing_original "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-10-missing-original -Command 'uv run pytest tests/test_context_offload_v4.py -q -k missing_original' -Evidence evidence/task-10-offload-error.txt"
    Expected: evidence/task-10-offload-error.txt contains exit_code: 0 and tests assert OFFLOAD_ORIGINAL_MISSING or equivalent exact error.
    Evidence: evidence/task-10-offload-error.txt
  ```

  Commit: YES | Message: `feat(context): add reversible offload` | Files: [`src/chat_lms_agent/context_offload.py`, `src/chat_lms_agent/context.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `tests/test_context_offload_v4.py`, existing context/privacy tests]

- [ ] 11. Add verifier-gated goal runtime

  What to do: Add tests first for `goal status`, `goal evidence add`, and `goal verify`. Store host-neutral goal records in private profile state with objective, subgoals, evidence refs, blockers, approval refs, trace refs, QA verifier status, and next action. Verification must fail unless tests/evidence/trace or approval references satisfy the goal requirements. Existing closeout should surface active goal obligations.
  Must NOT do: Do not build a second orchestrator or coding-agent runtime. Do not allow text-only verifier notes without evidence refs. Do not mark blocked for ordinary uncertainty.

  Parallelization: Can parallel: YES | Wave 3 | Blocks: [] | Blocked by: [5, 8, 9, 10]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `src/chat_lms_agent/session_closeout.py` - existing closeout surface to include goal obligations.
  - Pattern:  `src/chat_lms_agent/journal.py:86` - trace refs for evidence linkage.
  - Pattern:  `src/chat_lms_agent/approvals.py:148` - pending approval IDs for goal status.
  - Pattern:  `src/chat_lms_agent/memory_handlers.py:136` - memory obligations already produce blocked status with drafts.
  - Pattern:  `scripts/qa/capture-command.ps1:1` - evidence capture helper.
  - Test:     `tests/test_session_closeout_v2.py` - closeout regression anchor.
  - External: `https://developers.openai.com/codex/app` - Codex app supports parallel threads and review/ship workflows; Chat LMS goal records should be evidence overlays, not a runtime replacement.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_goal_runtime_v4.py tests/test_session_closeout_v2.py tests/test_context_doctor_closeout_v3.py -q` exits 0.
  - [ ] `goal verify` fails with `GOAL_EVIDENCE_MISSING` until required evidence refs exist.
  - [ ] `goal evidence add` stores redacted evidence metadata and links evidence to trace/audit/approval refs when supplied.
  - [ ] `session summarize` or closeout includes active goal obligations and next action.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: goal evidence allows verification pass
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task11_goal "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-11-goal -Command 'uv run pytest tests/test_goal_runtime_v4.py -q; $p=Join-Path $env:TEMP ''chat-lms-v4-goal''; python -m chat_lms_agent goal status --profile-root $p --json' -Evidence evidence/task-11-goal.txt"
    Expected: evidence/task-11-goal.txt contains exit_code: 0 and goal status returns PASS with no active goals for a clean profile or a test-created active goal.
    Evidence: evidence/task-11-goal.txt

  Scenario: missing evidence prevents completion
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task11_goal_missing "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-11-goal-missing -Command 'uv run pytest tests/test_goal_runtime_v4.py -q -k evidence_missing' -Evidence evidence/task-11-goal-error.txt"
    Expected: evidence/task-11-goal-error.txt contains exit_code: 0 and tests assert GOAL_EVIDENCE_MISSING.
    Evidence: evidence/task-11-goal-error.txt
  ```

  Commit: YES | Message: `feat(goal): gate completion on verifier evidence` | Files: [`src/chat_lms_agent/goals.py`, `src/chat_lms_agent/goal_handlers.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `src/chat_lms_agent/session_closeout.py`, `tests/test_goal_runtime_v4.py`, closeout tests]

- [ ] 12. Add optional read-only MCP discovery adapter

  What to do: Add tests first for an optional `mcp serve --profile-root <root> --read-only --transport stdio` command. If MCP dependencies are absent, return a precise JSON error without crashing. If present, expose only read-only discovery resources: public tool registry, side-panel catalog, skill catalog, redacted context summary, academy DB schema/query names, memory keys/summaries, approval/audit/trace indexes, and offload/context-map refs. Keep adapter disabled by default and do not add default dependencies unless a separate dependency review approves them.
  Must NOT do: Do not expose write tools. Do not expose raw private learner records, generated reports, secrets, or raw offload originals. Do not start an always-on listener.

  Parallelization: Can parallel: YES | Wave 3 | Blocks: [] | Blocked by: [1, 3, 4, 7, 8, 9, 10]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `pyproject.toml:7` - project currently has no runtime dependencies.
  - Pattern:  `pyproject.toml:13` - console script entry point should remain intact.
  - Pattern:  `src/chat_lms_agent/context.py:31` - adapter should read canonical context contracts.
  - Pattern:  `src/chat_lms_agent/agent_tools.py:96` - public tool registry payload.
  - Pattern:  `src/chat_lms_agent/journal.py:86` - trace index source.
  - Pattern:  `src/chat_lms_agent/approvals.py:18` - approval context source.
  - External: `https://developers.openai.com/codex/mcp` - Codex MCP supports local stdio servers and configuration; server instructions should be concise.
  - External: `https://developers.openai.com/api/docs/guides/tools-connectors-mcp` - MCP tool use can require approval; Chat LMS must keep discovery read-only.
  - External: `https://packaging.python.org/en/latest/specifications/pyproject-toml/` - optional dependencies belong under project optional dependency metadata when approved.

  Acceptance criteria (agent-executable only):
  - [ ] `uv run pytest tests/test_mcp_discovery_v4.py tests/test_repo_privacy.py -q` exits 0.
  - [ ] Without optional MCP dependency installed, command exits nonzero with `MCP_OPTIONAL_DEPENDENCY_MISSING`.
  - [ ] With dependency available in CI/dev extra, adapter exposes only read-only resources and no write tools.
  - [ ] Redaction tests cover private profile paths, learner-like names, secrets, reports, and offload originals.
  - [ ] No default install dependency is added to `[project].dependencies`.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: missing optional MCP dependency is explicit
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task12_mcp_missing "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-12-mcp-missing -Command '$p=Join-Path $env:TEMP ''chat-lms-v4-mcp''; python -m chat_lms_agent mcp serve --profile-root $p --read-only --transport stdio --json; if ($LASTEXITCODE -ne 0) { exit 0 } else { exit 1 }' -Evidence evidence/task-12-mcp.txt"
    Expected: evidence/task-12-mcp.txt contains exit_code: 0 and output includes MCP_OPTIONAL_DEPENDENCY_MISSING unless the optional dependency was intentionally installed.
    Evidence: evidence/task-12-mcp.txt

  Scenario: attempted write tool access is rejected
    Tool:     tmux + powershell
    Steps:    tmux new-session -d -s v4_task12_mcp_write "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name task-12-mcp-write -Command 'uv run pytest tests/test_mcp_discovery_v4.py -q -k write_rejected' -Evidence evidence/task-12-mcp-error.txt"
    Expected: evidence/task-12-mcp-error.txt contains exit_code: 0 and tests assert MCP_WRITE_TOOL_REJECTED or equivalent exact error.
    Evidence: evidence/task-12-mcp-error.txt
  ```

  Commit: YES | Message: `feat(mcp): add read-only discovery adapter` | Files: [`src/chat_lms_agent/mcp_adapter.py`, `src/chat_lms_agent/mcp_handlers.py`, `src/chat_lms_agent/command_parser.py`, `src/chat_lms_agent/commands.py`, `pyproject.toml` only if adding optional extras, `tests/test_mcp_discovery_v4.py`, privacy tests]

## Final verification wave (MANDATORY - after all implementation tasks)
> Runs in PARALLEL. ALL must APPROVE. Surface results to the caller and wait for an explicit "okay" before declaring complete.
- [ ] F1. Plan compliance audit - every task done, every acceptance criterion met
- [ ] F2. Code quality review - diagnostics clean, idioms match, no dead code
- [ ] F3. Real manual QA - every QA scenario executed with evidence captured
- [ ] F4. Scope fidelity - nothing extra shipped beyond Must-Have, nothing Must-NOT-Have introduced

Final verification commands:
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run basedpyright`
- `git diff --check`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name final-v4-tests -Command 'uv run pytest -q' -Evidence evidence/final-v4-tests.txt`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\capture-command.ps1 -Name final-v4-lint -Command 'uv run ruff check .; uv run basedpyright; git diff --check' -Evidence evidence/final-v4-lint.txt`

Agent team requirement:
- Coding Agent: owns implementation by task file boundaries above, one logical commit per completed task.
- QA/Testing Agent: independently runs all acceptance commands and tmux QA scenarios, reviews evidence, and must not share the Coding Agent's assumptions.
- Both agents run in dedicated tmux windows, e.g. `Codex -w v4-coding-agent --tmux` and `Codex -w v4-qa-testing-agent --tmux`.

## Commit strategy
- One logical change per commit. Conventional Commits (`<type>(<scope>): <subject>` body + footer).
- Atomic: every commit builds and passes tests on its own.
- No "WIP" / "fix typo squash later" commits on the final branch - clean up before merge.
- Reference the plan file path in the final commit footer: `Plan: plans/harness-v4-implementation-wave-plan.md`.
- Commit order should follow dependency order: Tasks 1-5 can land independently, then Tasks 6-9, then Tasks 10-12, then final verification/doc polish if needed.

## Success criteria
- All Must-Have shipped; all QA scenarios pass with captured evidence; F1-F4 approved; commit history clean.
- Public repo remains publish-safe under `uv run pytest tests/test_package_import.py tests/test_repo_privacy.py -q`.
- Full suite, lint, and type checks pass: `uv run pytest -q`, `uv run ruff check .`, and `uv run basedpyright`.
- Chat LMS Agent remains a Codex Desktop app harness today and transition-ready through host-neutral contracts, with no replacement runtime, no default proxy/wrapper, no default cloud memory, and no write-capable MCP surface.
