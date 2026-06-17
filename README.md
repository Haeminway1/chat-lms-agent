# Chat LMS Agent

A public-safe **harness** for a local teacher LMS agent. Codex Desktop runs
the AI agent; this repo is the deterministic command surface, safety gates,
ledgers, and memory around it. The teacher's interface is natural Korean
conversation; every risky operation needs a human-present approval, and all
real data lives in a private workspace outside this repo.

- Product intent and phases: **[PRD.md](PRD.md)**
- Structure map (start here to navigate the code): **[docs/architecture.md](docs/architecture.md)**
- Plan history and status: **[plans/STATUS.md](plans/STATUS.md)**
- Teacher setup, daily 기입, ClassCard, and session-log review: **[docs/teacher-runbook.md](docs/teacher-runbook.md)**
- Codex plugin / marketplace registration (manual install): **[codex-plugin/README.md](codex-plugin/README.md)**

## What the harness does today

- **Lifecycle hooks** for every session event (SessionStart through Stop),
  including a pre-execution safety gate and a knowledge-closeout gate that
  blocks session end with copy-paste Korean remediation commands.
- **Single-use, human-present approvals** — typed confirmation in a real
  terminal; the agent cannot approve itself.
- **Budgeted, deterministic context injection** with local top-K memory
  recall (Korean + English, no embeddings).
- **Gated runtime extensibility** — agent tools, side-panel blocks, and
  prompt-route packs grow through draft → evidence → teacher-approval
  pipelines.
- **Model & host independence posture** — a role→family→concrete model
  catalog and a single host-adapter module, proven by a fake-host
  end-to-end test. Codex Desktop remains the only supported runtime.
- **Privacy enforcement** — repo-wide privacy scans, secret/path redaction,
  and two-mode learner-PII pseudonymization on every model-bound text.
- **Deterministic DB writes (기입)** — a generic `write-action` engine compiles
  data-defined templates (`write-action-v1`) to fixed parameterized SQL (no
  arbitrary SQL, no joins), runs them in one backed-up atomic transaction with
  an ID/count-only audit row, and gates `apply` on a teacher-approved
  registration. Recording a class day (attendance / homework / progress /
  scores) becomes one command instead of hand-written SQL; new write
  capabilities are added as data templates, not code.
- **Automatic session transcript logging** — every Codex session (prompts, the
  agent's narrated messages and tool sequence, each tool call with arguments and
  output, token usage, per-turn model/approval posture) is ingested from the
  Codex rollout into a durable, owner-facing review log in the private workspace.
  Two native triggers (the Codex `notify` program and a detached SessionStart
  catch-up) run it fire-and-forget, so it never slows a live session; secrets and
  paths are stripped and learner names pseudonymized on disk. See
  [docs/session-logging.md](docs/session-logging.md).

~120 modules under `src/chat_lms_agent/`, 440+ hermetic tests, zero runtime
dependencies. CI runs a Windows-primary lane (`.github/workflows/ci.yml`).

## Development

```bash
uv sync --dev
uv run pytest          # full suite (hermetic; never touches real profiles)
uv run ruff check      # select=ALL
uv run basedpyright    # typeCheckingMode=all
```

Add tests before production code. Docs are contracts
(`tests/test_docs_contract.py`); the repo must stay publishable
(`tests/test_repo_privacy.py`).

## Real-Use Workspace

Use this repo for development. Use a private profile workspace for real
teaching data.

Create or refresh a private workspace with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -Mode User -Profile teacher-name
```

That workspace lives under the user's local app data folder and contains
real DB files, reports, backups, logs, and private memory. It is
intentionally separate from this public repository so the repo can stay
safe to publish.

The private workspace SessionStart hook auto-syncs safe runtime wiring from
this repo, so generated hook/AGENTS/profile changes follow development
without the teacher remembering a manual command. Data imports, DB
migrations, credentials, external writes, and destructive changes still
require explicit approval — from a real terminal, with the approval id
typed by hand.

## Isolated real-use environment

A teacher who also runs other Codex tooling (global dev plugins, multi-agent
orchestrators, telemetry) should not have that tooling bleed into real
lesson sessions — it slows simple actions and is a privacy concern around
learner data. So `bootstrap.ps1 -Mode User` also **provisions a clean,
isolated teacher `CODEX_HOME`** plus a labeled launcher: a separate Codex
home that loads **only** the chat-lms plugin (no third-party plugins, no
agent-orchestration manifesto merge, no telemetry), while the developer's
own `~/.codex` stays untouched. The teacher launches real-use sessions from
the generated launcher; everything else they have installed keeps working
elsewhere.

Step-by-step setup (download → isolated env → first 기입) is in
**[docs/teacher-runbook.md](docs/teacher-runbook.md)**.
