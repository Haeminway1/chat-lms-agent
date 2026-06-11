# Plan Status

Plans are historical design records. Current truth is `docs/architecture.md`
plus the test suite; read plans for rationale, not for current behavior.

| Plan | Scope | Status |
| --- | --- | --- |
| `chat-lms-agent-harness-v1-wave-plan.md` | First harness wave (hooks, memory, doctor) | Completed (earlier waves) |
| `harness-strengthening-implementation.md` | Tool guards, context doctor | Completed (earlier waves) |
| `harness-v2-agentic-hardening-plan.md` | Hook payloads, obligations, academy DB boundary | Completed (earlier waves) |
| `codex-desktop-transition-ready-harness-v3-plan.md` | Ledgers, approvals, host-neutral envelope | Completed (earlier waves) |
| `harness-v3-red-test-execution.md` | V3 red-test execution notes | Completed (earlier waves) |
| `chat-lms-agent-db-side-panel-harness-plan.md` | Academy DB + side-panel contracts | Completed (earlier waves) |
| `chat-lms-agent-self-maintaining-harness.md` | Self-syncing private runtime; specified the Stop decision contract | Completed (decision contract shipped with P0) |
| `harness-v4-oss-reference-expansion-plan.md` | OSS reference registry, context offload, goal ledger | Completed (earlier waves) |
| `harness-v4-implementation-wave-plan.md` | V4 implementation waves | Completed (earlier waves) |
| `harness-p0-remediation-wave-plan.md` | Gap-analysis P0: hermetic tests, CI, store composition, approval presence, hook contracts, PreToolUse gate, context diet | **Completed 2026-06-11** |
| `harness-v5-extensibility-and-independence-plan.md` | Block lifecycle, route packs, model catalog, host adapter, envelope ingress, PII contract, self-QA ledger | **Completed 2026-06-11** (wordbook route still built-in; packs are additive) |
| `gws-integration-plan.md` | Google Workspace: onboarding OAuth setup, calendar/sheets/drive/gmail-send CLI, approval-gated send, anti-browser-fallback routes | **Waves 1–3 implemented 2026-06-11** — standard-library only (no `[gws]` extra needed; deviation from plan, core stays dependency-free). Toss-style setup: embedded-default client slot (`EMBEDDED_CLIENT_ID`) + `gws client install` auto-detects the downloaded client JSON; the onboarding skill directs the agent to drive the one-time console flow via browser (user only logs in; publishing status must be In production). Remaining: owner runs the assisted console flow once and embeds the client; Wave 4 composite flows (word-test publish chain, side-panel schedule view) |

## ClassCard migration (single-OSS-repo distribution)

The ClassCard automation moved from the private predecessor repo so that
`chat_lms_agent` is the only repo shipped to users.

- **Phase A — done (2026-06-11):** eight interaction-core modules vendored
  (`classcard_login`, `classcard_browser`, `classcard_direct_*`); Playwright
  as the `[classcard]` optional extra; CLI verbs `login`, `direct-upload`,
  `direct-repair-audio` wired; static registry entry + `routes/classcard.json`
  so the tool is discoverable in hydration and reuse-check. Vendored files
  carry scoped lint/type relaxations.
- **Phase B — done (2026-06-11):** the DB-integrated planning flow is wired.
  `classcard upload --student <name>` reads the lesson words the side-panel
  wordbook stores in the profile DB (`tutoring_*` tables, verified against
  live data shape), builds the part plan/manifest/TSVs, records the run in
  `classcard_upload_runs`, and `--execute` drives the proven headless
  uploader; `recover`/`verify` round-trip checkpoints. Tests seed a fully
  synthetic schema (no learner data). Remaining debt: vendored-module
  lint/type relaxations (`classcard*.py`) to be paid down opportunistically.

Open follow-ups are tracked in the gap-analysis roadmap (local draft):
migrate the built-in wordbook route into `routes/wordbook.json`, add doctor
rows for model-catalog validate and the QA ledger, ClassCard Phase B, and
the P1/P2 backlog (Korean message catalog, file locking, Windows toasts,
session search, nightly maintenance, skill playbooks).
