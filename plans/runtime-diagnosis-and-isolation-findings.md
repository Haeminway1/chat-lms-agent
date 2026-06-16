# Runtime Latency Diagnosis + Codex Environment Isolation — Findings

Status: **FINDINGS (saved record).** Three investigation passes on 2026-06-16
(latency forensics → write-capability design → runtime-isolation forensics), each
run as a multi-agent workflow with adversarial verification against the live machine,
config, Codex session logs, and private DB. This file is the durable record so the
analysis is not lost to context. Companion design: `academy-write-workflow-engine-plan.md`.

Scope note: real-use sessions run in the PRIVATE workspace
`<profile-root>\codex-workspace`; the public dev repo is `<repo-root>`. All learner data
is in the private `<profile-root>\data\chat_lms.db` and must never enter the public repo.

---

## Part 1 — Why simple ops take 2–4 minutes

Measured from the real 2026-06-15 Codex rollout
`~/.codex/sessions/2026/06/15/rollout-…019ec937…jsonl` (cwd = codex-workspace).

| Operation | Wall | LLM improvisation | Real subprocess work |
| --- | --- | --- | --- |
| 뷰어 열기 | 210s | 199s (95%) | 10.6s (opener 3.45s) |
| EBSS 기입 | 261s | 250s (96%) | 11.1s (DB write **0.46s**) |
| EIS 기입 | 236s | 230s (97%) | 6.1s |
| EISS 기입 | 195s | 189s | 5.8s |
| M1A 기입 | 133s | 129s | 4.0s |
| 일지 보기 | 75s | 73s | 2.0s |

**Dominant cause (85–95%): no deterministic write path for 기입.** The harness
`academy-db` CLI is read-only (named queries `learner-count`/`class-count` only); the
`agent-tools` `academy-db` entry is `status:"planned"` — a placeholder never built. So
the agent re-derives schema, resolves class/student/test IDs, and **hand-writes a
multi-table raw-SQL transaction** every class. The 06-15 session shows ~32 separate raw
`INSERT` exec calls (14 sessions, 10 student_session_records, 4 test_results, 4 tests)
+ lookups; 89 model round-trips at ~2.82s median over a growing ~120K-token context.
The actual write executes in 0.46s.

Verified write target = private `data/chat_lms.db`: `sessions` (class day) → trigger
`trg_sessions_auto_student_session_records` auto-stubs `student_session_records` from
active enrollments → `test_results` (needs parent `tests` row) → `curriculum_entries`.
A legacy predecessor "lite" DB's `agent_actions.action_type='record_class'` one-shot writer
existed and was **never ported** to the new harness. **Data bug:** 06-15 session 579
has `attendance=NULL` on all 8 student rows (others filled) — an improvisation
inconsistency to repair once a deterministic writer exists.

**Secondary / conditional — per-tool-call hook tax (~1.85–2.7s/call).** Codex fires
PreToolUse+PostToolUse per tool call, each a 4-process pipeline (dispatcher PowerShell →
dir-walk → `chat-lms-cli.ps1` which runs a redundant `py -3` version pre-check → `py -m
chat_lms_agent hook`). Real and costly **when it fires**, but the 06-15 teacher rollouts
show ZERO per-tool hook-execution events, so this was NOT the cause of the observed
slowness — it is a latent cost. SessionStart hydrate DID run and re-runs the full
`bootstrap.ps1` every session (~1.1s, ~2.3s on the self-rewrite reentry).

**Refuted:** the Stop closeout gate is not the culprit — on this profile all block
branches are empty (obligation keys already present, no tools.json, no pending
approvals), so it returns PASS; it never fired in the slow session.

Measured latencies: bare python ~87ms; `import chat_lms_agent` 107ms; full
`doctor --json` cold 1.24s; `hook user-prompt-submit` 415ms; host-context payload 9.2KB.

---

## Part 2 — The codex-workspace runtime is contaminated by the dev tooling

Real-use teacher sessions share the dev `~/.codex` home, so the developer's global
multi-agent dev stack loads into PII-handling teacher sessions. Verified live.

**Channel 1 (highest) — global AGENTS.md manifesto merge.** `config.toml`
`child_agents_md=true` force-merges `~/.codex/AGENTS.md` — the full "Sisyphus
Multi-Agent System / THE BOULDER NEVER STOPS / spawn agents / /ultrawork / Agent Team
Rules MANDATORY" manifesto — into EVERY session as standing context (no hook needed).
Confirmed in rollouts 019ec8d2/019ec937 as an ~11.5K-char "AGENTS.md instructions for
…codex-workspace" record concatenating the Sisyphus manifesto with the teacher AGENTS.md.

**Channel 2 — `omo@sisyphuslabs` UserPromptSubmit steering.** `ultrawork`/`ulw-loop`
hooks. Confirmed live: the one-line teacher request "fix the student DB to match the
Google Sheet" (rollout 019ebaba) triggered `<ultrawork-mode>` (×2), `create_goal` (×4),
~25 spawn_agent/multi_agent references, C001–C003 success criteria, adversarial verify,
and a full `.omo/ulw-loop/019ebaba-…/` evidence tree (brief.md, real student
academy-report HTML, db-diffs, quality-gate.json) **written into the private workspace**.
A 30-second UPDATE became a heavy multi-agent orchestration — directly fighting the
workspace's own "reliability and speed over framework purity" rule.

**Channel 3 — code MCP servers in the tool surface.** `omo .mcp.json` declares 5
(ast_grep, grep_app[remote], context7[remote], git_bash, lsp); on THIS Desktop only
`context7` + `git_bash` are enabled. `git_bash` was used 52× in 019ec937 as slow
indirection over plain shell; `context7` (remote) loaded but 0 calls — an armed,
unused, potential student-PII exfil channel. (Earlier "5 servers" was overstated.)

**Channel 4 — SessionStart provisioning.** omo runs rules + telemetry(PostHog) +
auto-update(network) + bootstrap(daemon) every session, alongside the chat-lms hydrate.

**Privacy:** PostHog telemetry sends a machine fingerprint + daily-active heartbeat
(SHA256 hostname; NOT prompt/DB contents; last fired 2026-06-04); auto-update makes
network checks; remote `context7` is the latent PII channel. None gate to the teacher
workspace. Opt-out: `OMO_DISABLE_POSTHOG=1` / `OMO_SEND_ANONYMOUS_TELEMETRY=0`.

**Reconciliation with "hooks never fire under Codex":** per-tool Pre/Post hook EVENTS
were absent in transcripts, but the contamination that matters most needs no hook — the
AGENTS.md merge is native Codex project-instruction loading, MCP servers load into the
tool surface, and SessionStart provisioning runs regardless.

---

## Part 3 — Isolation: a separate `CODEX_HOME` (verified for Desktop)

**Decision: isolate teacher real-use into its own clean `CODEX_HOME`**, e.g.
`~/.codex-teacher` (a dedicated teacher home), launched via a shortcut/.cmd that sets
`$env:CODEX_HOME` BEFORE activating Desktop (after fully quitting the single-instance
dev Desktop). Dev `~/.codex` stays 100% intact (keeps Sisyphus).

**Why this mechanism (others verified to fail):**
- Desktop **can** take an alternate home: it is a FullTrust MSIX
  (`OpenAI.Codex_2p2nqsd0c76g0`, AUMID `…!App`) that inherits the activating
  environment; `codex doctor`/`plugin list` with a throwaway `CODEX_HOME` redirected
  auth/socket/daemon/config and showed "No marketplace plugins found". `CODEX_HOME` is
  currently unset at User/Machine scope, so Desktop runs the contaminated default today.
- `--profile` does NOT work: `codex app` has no `--profile` flag, and profiles only
  LAYER scalar keys on the same base config — they cannot subtract plugins, remove
  `[agents.*]`, or un-merge the AGENTS.md manifesto.
- Per-project `.codex/config.toml` cannot disable a globally-enabled plugin/feature or
  opt out of the AGENTS.md merge (only `plugins.<p>.mcp_servers.<s>.enabled`).
- Second install is pointless — isolation is a function of `CODEX_HOME`, not the binary.

**Clean teacher `config.toml` (minimal):** `model="gpt-5.5"`; approval/sandbox posture
(speed: `never`/`danger-full-access`, or safer: `untrusted`/`workspace-write`);
`[features] plugins=true, plugin_hooks=true` and **deliberately omit
`child_agents_md`/`multi_agent`/`enable_fanout`** (omitting `child_agents_md` is the key
line that kills the manifesto merge); `[projects.'…codex-workspace'] trust_level="trusted"`;
`[marketplaces.chatlms] source='<repo-root>\codex-plugin'`;
`[plugins."chat-lms-agent@chatlms"] enabled=true`; **NO omo, NO `[agents.*]`, NO
`shell_environment_policy.set`.** Launch by AUMID from an env-set `.cmd` (survives
Desktop updates better than the version-stamped exe path).

**Orthogonal to the write-engine plan:** chat-lms is keyed by absolute paths +
`.chat-lms-profile.json` (repo grep for `CODEX_HOME` = 0 hits), so hydrate, routing,
the PreToolUse safety gate, and the planned `write-action` engine work unchanged under
the clean home. write-action register/approve must run from a real PowerShell TTY
(Desktop has none). Isolation also REMOVES the ultrawork "heavy tiering / never stop"
steering — the very pressure that turns a fast op into an orchestration — so it makes
the write-engine's and the (still-missing) READ-fast-path's speed goals achievable.

**Manual touch points (Codex security; cannot be fully automated):** fully quit the
running Desktop first (single-instance); one-time `codex login` per home; one-time
chat-lms hook-trust approval. NEVER set `CODEX_HOME` at User/Machine scope (would strip
Sisyphus from dev) — keep it in the launcher, or use a dedicated Windows teaching
account with `CODEX_HOME` at that account's User scope (strongest, footgun-free).

**Cleanups:** delete the dev-orchestration litter already written into the private
workspace (`…\codex-workspace\.omo\ulw-loop\019ebaba-…\`, contains real student data);
optionally disable omo telemetry in the dev home too.

---

## Open follow-ups

- **READ fast-paths are still missing** (e.g. "오늘 EBSS 기록 보여줘") — same
  improvisation cost as writes; design alongside the write engine.
- **`pre_tool_gate` does not block raw sqlite writes** to `data/chat_lms.db` (not in
  `_PRIVATE_DATA_MARKERS`) — the engine is the easier path, not the only one; add the DB
  path to the markers so writes funnel through the CLI.
- **Distribution/product requirement (new):** bootstrap should AUTO-create the isolated
  teacher `CODEX_HOME` + labeled launcher on install, so any instructor (even one with a
  global dev stack like omc) gets a clean, contamination-free chat-lms workspace without
  hand-editing config. See the build plan for this once approved.
