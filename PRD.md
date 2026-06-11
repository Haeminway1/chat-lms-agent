# Chat LMS Agent — Product Requirements

## Product

A local LMS (learning management) agent for a single Korean teacher. The
teacher's interface is natural Korean conversation with an AI agent; this
repository is the **harness** around that agent — the deterministic command
surface, safety gates, ledgers, and memory that make the conversation safe
and repeatable. The harness never runs an LLM loop itself.

## Users

- **Teacher (operator, non-developer)** — talks to the agent in Korean,
  approves risky operations from a real terminal, owns all learner data.
- **Developer (owner)** — evolves the harness in this public repo through
  TDD; never commits private data.

## Phases

| Phase | Host | Status |
| --- | --- | --- |
| 1 | Codex Desktop runs the agent; this harness drives it through lifecycle hooks | **Current — the only supported runtime** |
| 2 | Standalone desktop app (own loop, same harness core) | Prepared, not started |
| 3 | Web SaaS (multi-tenant, same harness core) | Prepared, not started |

Phase 2/3 readiness is engineering posture, not a roadmap commitment: the
host adapter (`src/chat_lms_agent/hosts.py`), the neutral event envelope
(`harness-event-v1`), and the model catalog (`docs/model-catalog.json`)
exist so the host and model can be swapped without rewriting the core. A
fake-host end-to-end test proves the full session cycle runs without any
host-specific field names.

## Core requirements (implemented)

1. **Public/private boundary** — runtime state can never live under the
   public repo; every outbound text passes secret/path redaction and
   learner-PII pseudonymization (reversible only on owner surfaces).
2. **Human-present approvals** — risky operations require a teacher approval
   from an interactive terminal with a typed approval id; approvals are
   single-use; the agent cannot approve itself.
3. **Pre-execution safety gate** — destructive commands against private
   data, direct writes to runtime ledgers, and private references landing in
   public files are denied before they run.
4. **Knowledge closeout** — sessions cannot end cleanly while required
   memory records, pending approvals, or unapplied import plans remain; the
   block message carries copy-paste Korean remediation commands and
   escalates to the teacher after three identical blocks.
5. **Context discipline** — injected context is deterministic, byte-budgeted
   per section, tiered by event, and memory recall is local keyword top-K
   (no embeddings, no extra LLM calls).
6. **Gated extensibility** — new agent tools, side-panel blocks, and prompt
   routes grow at runtime through draft → evidence → teacher-approval
   pipelines; production surfaces never load unreviewed drafts.
7. **Model/host independence** — model identity resolves through a
   role → family → concrete catalog with teacher overrides; only one module
   knows the host by name (enforced by an architecture test).

## Non-goals (deliberate)

- No replacement LLM loop, provider router, or subagent process manager
  while Codex Desktop is the host.
- No messaging gateways or remote/embedding memory backends — learner data
  never leaves the machine.
- No autonomous memory or skill self-promotion — automation may *suggest*,
  only the teacher promotes.
- No writes to host-owned configuration files.

## Quality gates

`uv run pytest` (199 tests, hermetic), `ruff check` (select=ALL),
`basedpyright` (typeCheckingMode=all), and the Windows-primary CI lane in
`.github/workflows/ci.yml` must stay green. Repo privacy scans and
docs-contract tests gate every change.

## Where to read next

- Structure map: `docs/architecture.md`
- Plan history and status: `plans/STATUS.md`
- Terminology contract: `docs/terminology.md`
