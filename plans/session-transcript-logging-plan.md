# Session Transcript Logging — Design + Execution Plan

Status: **DESIGN (ready to execute).** Goal: every Codex session run by the
teacher is automatically recorded into a durable, reviewable transcript log —
what the teacher asked, the agent's narrated thinking and tool sequence, every
tool call + arguments + output, token usage, and the model/approval/sandbox
posture per turn — so the operator can review after the fact whether the agent
worked correctly and improve it. Logging must be **automatic** and **never
affect a live session** (zero hot-path latency, can never break a turn).

Companion findings: `runtime-diagnosis-and-isolation-findings.md` (why per-tool
hooks do not fire under Codex; the isolated teacher `CODEX_HOME`).

---

## 1. Source of truth: the Codex rollout JSONL

Codex Desktop already writes a complete per-session transcript to
`<CODEX_HOME>/sessions/YYYY/MM/DD/rollout-<ISO>-<uuid>.jsonl`. Each line is
`{timestamp, type, payload}`. We do **not** re-capture anything live; we ingest
this file. Field map (verified against live rollouts):

| line `type` | `payload.type` | what we extract | normalized `kind` |
| --- | --- | --- | --- |
| `event_msg` | `user_message` | `payload.message` | `user_prompt` |
| `event_msg` | `agent_message` | `payload.message` (+ `phase`) | `agent_message` |
| `response_item` | `message` | `payload.role`, `payload.content[].text` | `user_prompt`/`agent_message`/`developer_context` |
| `response_item` | `reasoning` | **summary empty, encrypted_content opaque** | `reasoning` (marker only) |
| `response_item` | `function_call` | `payload.name`, `payload.arguments` (JSON string), `payload.call_id` | `tool_call` |
| `response_item` | `function_call_output` | `payload.call_id`, `payload.output` | `tool_output` |
| `event_msg` | `token_count` | `payload.info.total_token_usage.*` | `usage` |
| `turn_context` | — | `model`, `cwd`, `approval_policy`, `sandbox_policy.type`, `effort` | `turn_context` |
| `session_meta` | — | `id`, `cwd`, `originator`, `cli_version`, `git.*` | `session_meta` |

**Honest limitation:** the agent's private chain-of-thought is **encrypted by
Codex** (`reasoning.summary == []`, `encrypted_content` opaque). We record that
reasoning occurred (with surrounding token counts and the visible
`agent_message` narration + tool sequence that reveal the de-facto reasoning),
but the raw hidden CoT is not recoverable by anyone.

## 2. Triggers (both, per operator decision)

1. **Native Codex `notify` (live, per-turn).** Codex runs a configured program
   on turn end (`notify = ['powershell', ... , '-File', '<...>\chat-lms-notify.ps1']`),
   appending the event JSON as the final argv. This fires natively — it does not
   depend on the plugin hooks that never fire under Codex. Bootstrap wires it into
   the isolated teacher `config.toml` (collision-free; no notify exists there).
   The notify program invokes `session-log ingest`; it is fire-and-forget from
   Codex's side, so it adds no user-facing latency.
2. **SessionStart catch-up (safety net).** The generated `session-start-hydrate.ps1`
   launches `session-log ingest` **detached** (`Start-Process -WindowStyle Hidden`,
   no `-Wait`), in its own `try/catch`, after emitting context. Guarantees any
   session that ended without a final notify (crash, notify-not-honored) is still
   flushed on the next launch. Zero added latency to hydrate.
3. **Manual** `session-log list|show|export` for review (and `ingest` on demand).

Both triggers call the same idempotent `ingest`; concurrency is serialized by a
lock (below), so double-firing is safe.

## 3. New module `src/chat_lms_agent/session_ledger.py`

Mirrors `self_qa.py` (append-only JSONL) + `journal.py` (redaction). All state
under `profile.root / STATE_DIR / "session-logs"`; never the repo
(`resolve_profile_state` rejects repo roots → exit 4). Per-session file
`session-logs/<sanitized-session-id>.jsonl`; checkpoint/index
`session-logs/_ingest-state.json`; lock `session-logs/_ingest.lock`.

Public API:
- `ingest_rollouts(profile, *, codex_home=None) -> dict` — locate sessions dir,
  acquire lock (skip if held), scan rollout files newer than checkpoint, read
  only **complete** lines past each file's stored line-offset, normalize, redact,
  append to the per-session log, advance offsets, update index, prune retention.
  Defensive: never raises; returns a status summary.
- `list_sessions(profile) -> dict` — index roll-up (id, started_at, cwd, model,
  prompt/tool/error counts, last_ts).
- `show_session(profile, session_id) -> (exit, dict)` — normalized records with
  pseudonyms **restored** for the owner (`privacy.restore_text`).
- `export_session(profile, session_id=None, *, reveal=False) -> (exit, dict)` —
  default keeps pseudonyms (safe to share); `--reveal` restores.
- `set_enabled(profile, enabled) -> dict`, `is_enabled(profile) -> bool`
  (default **True**).

Normalized record (fixed fields; free text confined to redacted, length-capped
fields so PII cannot ride elsewhere):
`schema_version, session_id, ts, kind, text, tool_name, tool_args, tool_output,
call_id, model, approval, sandbox, effort, tokens, cwd, encrypted, truncated`.

**Redaction (operator decision: pseudonymize on disk + restore on read).**
Every persisted free-text field goes through `journal.redact_runtime_text`
(secret/token/absolute-path redaction → `<profile-root>`/`<repo-root>` labels →
learner-PII `pseudonymize_text` last). `show`/`export --reveal` restore via
`privacy.restore_text`. Secrets/paths are **always** stripped regardless.

**Bounds / safety:**
- Per-field cap `FIELD_MAX_CHARS` (truncate, set `truncated=true`).
- Per-run line cap `INGEST_MAX_LINES_PER_RUN` (leftover flushed next trigger).
- Per-session-file byte cap `SESSION_FILE_MAX_BYTES` (stop appending, mark index).
- Retention `MAX_SESSION_FILES` (prune oldest by mtime during ingest).
- Lock via `os.open(O_CREAT|O_EXCL)`; stale-lock steal after `LOCK_STALE_SECONDS`.
- Locator order: `codex_home/sessions` → `$CODEX_HOME/sessions` →
  `profile.root/codex-home/sessions` (isolated teacher) → `~/.codex/sessions`.
- Idempotent: line-offset checkpoint; a partial last line (no trailing `\n`) is
  not consumed and is re-read next run.

## 4. CLI wiring

- `session_log_handlers.handle_session_log(args, repo_root)` mirrors `_handle_qa`
  (profile_state_or_error → verb → pure fn → write_json → exit code).
- `command_parser`: new `session-log` subparser with verbs `ingest|list|show|
  export|enable|disable|status`; `--session-id`, `--reveal`, `--json`, profile args.
- `commands._dispatch`: `"session-log": lambda a: handle_session_log(a, _repo_root())`.
- Not a 7th hook event (hooks.json stays the strict 6-event set).

## 5. Bootstrap triggers

- `Write-TeacherCodexHome`: add a top-level `notify = ['powershell', '-NoProfile',
  '-ExecutionPolicy', 'Bypass', '-File', '<workspace>\scripts\chat-lms-notify.ps1']`
  line **after** `network_access` and **before** `[features]` (config still
  `startswith('model = "gpt-5.5"')`; no `[plugins.`; no forbidden substrings;
  deterministic → idempotent).
- `Write-PrivateWorkspaceFiles`: author `chat-lms-notify.ps1` (bakes `$localRoot`
  + cli-wrapper path; reads the notify JSON from `$args[0]`; calls
  `chat-lms-cli.ps1 session-log ingest --profile-root <localRoot> --json`;
  swallows all errors).
- `sessionStartTemplate`: detached hidden `Start-Process` of the cli wrapper
  `session-log ingest` (placeholders `__CLI_SCRIPT_PATH__`, `__LOCAL_ROOT__`),
  wrapped in its own `try/catch`, after `New-AdditionalContextOutput`.

## 6. Docs (contracts)

- New `docs/session-logging.md` (storage path, privacy posture, triggers, CLI,
  the encrypted-reasoning limitation).
- `docs/architecture.md`: add a "Session transcript logging" subsection + the
  `session_ledger` anchor (locked by `test_docs_contract`).
- README bullet under "What the harness does today".

## 7. Test plan (TDD; hermetic via `_hermetic_env` + explicit `--profile-root`)

`tests/test_session_ledger.py`:
1. `_normalize_event` per item type → correct kind/fields (table-driven).
2. ingest synthetic rollout → per-session log has expected records.
3. idempotency: re-ingest same file → no new records; offset stable.
4. incremental: append new complete lines → only new records ingested.
5. partial last line (no `\n`) not consumed; completes next run.
6. redaction: token/secret/`C:\...` path in tool output → `[redacted]`; a
   configured learner name pseudonymized on disk (`[P:...]`).
7. `show_session` restores the pseudonym for the owner.
8. `export_session` default keeps pseudonym; `--reveal` restores.
9. `list_sessions` returns counts (prompt/tool/error).
10. enable/disable gates ingest; default enabled.
11. locator resolves `profile.root/codex-home/sessions`.
12. malformed lines / missing dir → no raise, status PASS.
13. concurrency lock: second ingest while lock held → skipped, no duplicates.
14. retention prunes oldest beyond `MAX_SESSION_FILES`.
15. PUBLIC_REPO_STATE_REJECTED via handler (exit 4).

`tests/test_session_log_cli.py`: subprocess `python -m chat_lms_agent session-log
ingest|list|show|status` round-trip with `--profile-root tmp`; exit codes; no raw
profile path in stdout.

`tests/test_bootstrap_session_log_wiring.py`: User-mode bootstrap into a temp env
asserts: config.toml contains `notify` + still `startswith('model = "gpt-5.5"')`
+ `[plugins.` count == 1 + no forbidden substrings; `chat-lms-notify.ps1` exists
and references `session-log ingest`; `session-start-hydrate.ps1` contains the
detached ingest launch; config idempotent across two runs.

Existing gates that must stay green: `test_bootstrap_v2.py`,
`test_hooks.py`, `test_repo_privacy.py`, `test_docs_contract.py`,
`test_conftest_hermeticity.py`, plus full `uv run pytest`, `ruff check`
(select=ALL, no new per-file ignores), `basedpyright` (typeCheckingMode=all).

## 8. Success / failure criteria

**Success:**
- New + existing tests green; `ruff check .`, `ruff format --check .`,
  `basedpyright` clean for the new module (zero relaxations).
- Ingest is idempotent, incremental, never raises, and writes only under
  `profile.root/.chat-lms-state/session-logs/`.
- Secrets/paths always redacted; learner names pseudonymized on disk, restored
  only on owner `show`/`--reveal`.
- Triggers add no measurable hydrate latency (detached) and notify is
  fire-and-forget; both safe under double-fire (lock).
- No 7th hook event; bootstrap config contracts preserved.

**Failure (any one):**
- A live session is blocked, slowed measurably, or errors due to logging.
- A transcript log can be written inside the public repo, or committed sample
  data trips `test_repo_privacy`.
- Raw learner PII or a secret/absolute path persists unredacted on disk.
- Ingest can raise out of the trigger path, or corrupts/loses the offset under
  concurrency, or double-appends.

## 9. Post-build adversarial QA remediation (round 2)

An independent 4-lens adversarial QA pass (privacy / hot-path / correctness /
gates) found defects the green gates missed; all fixed and regression-tested:

- **Secret VALUES leaked** (`sk-…`, `Bearer …`, `AKIA…`, GitHub PATs, JWTs, UNC
  paths bypassed the keyword-only redactor). Fixed by extending
  `state.redact_text` with high-signal credential patterns (benefits
  journal/trace/audit/memory too) + a redaction regression test.
- **Thousands of tool calls dropped** — the normalizer ignored
  `custom_tool_call(_output)`, `mcp_tool_call_end`, `patch_apply_end`,
  `exec_command_end`, `tool_search_call`, `web_search_call`, and plaintext
  `agent_reasoning`. Fixed with a dispatch-table normalizer covering all of
  them plus an `other` catch-all so future host event types are never lost.
- **`ingest_rollouts` could raise** (locator/lock ran before the `try`). Fixed by
  guarding the whole body and releasing the lock in `finally`; added a
  blocked-state-path regression test. Added a `repo-root` ingest guard so even
  the `--profile` fixture form cannot write into the repo.
- **Every ingest re-read the entire rollout corpus (~5s, unbounded)**. Fixed
  with byte-offset checkpoints + an `st_size` short-circuit (caught-up files
  cost one `stat()`), newest-session-first ordering, and pruning of offsets for
  vanished files. The `notify` script now self-detaches (`Start-Process`,
  hidden, no `-Wait`) so non-blocking is owned by the harness, not assumed of
  the host.
- **Docs accuracy**: name pseudonymization is opt-in via `privacy.json`;
  unconfigured phone/email is not pattern-redacted by default (private-workspace
  only) — documented honestly rather than overclaimed.

Residual, accepted (documented, low-risk, review-log-only): a crash in the
append→checkpoint window can duplicate records on the next run; the 4 MiB
per-session cap is intentional bounded loss; a profile path containing an
apostrophe would break the generated TOML (pre-existing pattern).
