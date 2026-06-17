# Session Transcript Logging

Every Codex session the teacher runs is recorded automatically so the operator
can review, after the fact, whether the agent worked correctly and improve it.
This is a read-only consumer of data Codex already writes; it never changes how a
live session behaves.

## What is captured

Codex Desktop writes a complete per-session rollout to
`<CODEX_HOME>/sessions/YYYY/MM/DD/rollout-*.jsonl`. `session_ledger.py` parses
that rollout into normalized, fixed-field records:

- `user_prompt` — what the teacher asked.
- `agent_message` — the agent's visible narration / final answers.
- `tool_call` — tool name, arguments, and `call_id`. Covers `function_call`,
  `custom_tool_call`, MCP calls (`mcp_tool_call_end`), and search/image calls.
- `tool_output` — the tool result, linked by `call_id`. Covers
  `function_call_output`, `custom_tool_call_output`, `exec_command_end`, and
  `patch_apply_end` (file list + stdout/stderr, with absolute paths redacted).
- `reasoning` — the host's private chain-of-thought is usually **encrypted**
  (`summary` empty, `encrypted_content` opaque) and is then recorded as a marker
  only (`encrypted: true`); when a plaintext `agent_reasoning`/`summary` is
  present it is captured (redacted). The visible narration and tool sequence
  reveal the de-facto reasoning regardless.
- `usage` — token counts (input / cached / output / reasoning / total).
- `turn_context` — model, approval policy, sandbox, reasoning effort.
- `session_meta` — originator, CLI version, git branch/commit.
- `other` — a catch-all so any future/unrecognized host event type is recorded
  rather than silently dropped.

## Where it lives

Per-session logs are append-only JSONL under the **private** profile workspace:

```text
<profile-root>/.chat-lms-state/session-logs/<session-id>.jsonl
<profile-root>/.chat-lms-state/session-logs/_ingest-state.json   # checkpoint + index
```

This is never written inside the public repo (`resolve_profile_state` rejects
repo roots), and the private workspace already holds the real DB and reports, so
the log shares that trust boundary. It must never be copied into the repo.

## Privacy

- Secrets, tokens, and paths are **always** redacted by `state.redact_text`:
  keyword forms (`TOKEN=…`, `secret: …`), high-signal credential *values*
  (`sk-…`, `Bearer …`, `AKIA…`, GitHub PATs, JWTs), and absolute / UNC paths
  (→ `<profile-root>`/`<repo-root>` labels or `[redacted]`). This runs on every
  free-text field before it is written.
- Learner names are **pseudonymized on disk** (`privacy.pseudonymize_text`, e.g.
  `민지` → `[P:a1b2c3d4]`) — but only for names **registered in the profile's
  `privacy.json`** (the harness's existing opt-in PII mechanism). Real names are
  restored only on the owner's `session-log show` and `export --reveal`, via a
  pure local lookup. Names are only pseudonymized once registered in
  `privacy.json` — there is currently no automatic roster seeding, so register
  the learners you want masked via the privacy registry (see
  `docs/academy-data-contract.md`).
- **Contact PII not registered in `privacy.json` (phone, email) is *not*
  pattern-redacted by default** — it is written verbatim to the on-disk log.
  This is acceptable because the log lives only in the private workspace
  (alongside the DB that already holds it) and never enters the repo; to strip
  it, add a one-way `privacy.json` entry (see `docs/academy-data-contract.md` /
  the privacy registry).
- Records are fixed-field; free text is confined to redacted, length-capped
  fields so learner data cannot ride along elsewhere. The log is never written
  under the public repo (`resolve_profile_state` + a `repo-root` ingest guard).

## How it runs automatically

Two native triggers, neither of which depends on the per-tool hooks that do not
fire under Codex Desktop:

1. Codex `notify` (per-turn, live). `bootstrap.ps1` wires a top-level `notify`
   line into the isolated teacher `config.toml` pointing at
   `chat-lms-notify.ps1`, which calls `session-log ingest`. Codex spawns it
   fire-and-forget at turn end, so it adds no user-facing latency.
2. SessionStart catch-up (safety net). The generated `session-start-hydrate.ps1`
   launches `session-log ingest` **detached** (hidden, no wait, its own
   try/catch), so any session that ended without a final notify is still flushed
   at the next launch.

Ingest is idempotent (per-file line-offset checkpoint; a partial last line is not
consumed until complete), serialized by an exclusive-create lock, and
retention/size bounded — so double-firing is safe and disk growth is bounded. It
never raises out of the trigger path.

## Reviewing logs

```powershell
# via the private workspace CLI wrapper (scripts/chat-lms-cli.ps1)
chat-lms-cli.ps1 session-log list --profile-root <root> --json
chat-lms-cli.ps1 session-log show --session-id <id> --profile-root <root> --json
chat-lms-cli.ps1 session-log export --session-id <id> --profile-root <root> --json   # safe (pseudonymized)
chat-lms-cli.ps1 session-log export --session-id <id> --reveal --profile-root <root> --json
chat-lms-cli.ps1 session-log status --profile-root <root> --json
chat-lms-cli.ps1 session-log disable --profile-root <root> --json   # pause logging
chat-lms-cli.ps1 session-log enable --profile-root <root> --json
```

`list` returns a per-session roll-up (model, prompt/tool/error counts, start and
last timestamps). `show` restores learner names for the owner; `export` keeps the
pseudonymized form unless `--reveal` is passed. Logging is on by default; only an
explicit `disable` turns it off.
