# Chat LMS Agent

A public-safe **harness** for a local teacher LMS agent. Codex Desktop runs
the AI agent; this repo is the deterministic command surface, safety gates,
ledgers, and memory around it. The teacher's interface is natural Korean
conversation; every risky operation needs a human-present approval, and all
real data lives in a private workspace outside this repo.

- Product intent and phases: **[PRD.md](PRD.md)**
- Structure map (start here to navigate the code): **[docs/architecture.md](docs/architecture.md)**
- Plan history and status: **[plans/STATUS.md](plans/STATUS.md)**

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

~55 modules under `src/chat_lms_agent/`, ~199 hermetic tests, zero runtime
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
