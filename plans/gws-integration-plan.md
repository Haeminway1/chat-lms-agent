# Google Workspace (gws) Integration Plan

## Purpose

Give the harness first-class Google Workspace commands — Calendar, Sheets,
Drive, and Gmail send — as a single optional extra, set up during teacher
onboarding with one browser consent. Primary teacher flows: uploading word
test sheets (Drive/Sheets) and managing the lesson schedule (Calendar),
plus sending test sheets to parents (Gmail).

Trigger incident: a fresh session improvised with browser automation
because "gws" existed only as an unregistered reference copy (a
hermes-agent skill vendored inside the predecessor repo's archive) with no
OAuth token, no executable, and no harness registration. This plan replaces
that dead end with a registered, onboarded, least-privilege integration.

## Plain-Language Model

The workshop gains a licensed courier. The courier gets one badge (OAuth
token) issued during onboarding; the badge only opens four doors (calendar
events, spreadsheets, files the courier itself created, outgoing mail).
Outgoing mail to a human additionally needs the teacher's stamp (approval
ledger) because a misaddressed letter cannot be unsent. The badge lives in
the teacher's drawer (user home), never in the repo, never in chat context.

## External Reference Decisions

| Reference | Decision | What To Adopt | What Not To Copy |
| --- | --- | --- | --- |
| hermes-agent `skills/productivity/google-workspace` (`google_api.py`, `setup.py`) | Structural reference (MIT; add to `docs/oss-reference-registry.md` with pinned SHA at implementation) | Token-file shape with refresh handling; scope-checked service builders; setup-wizard UX (one browser consent, paste-code fallback) | Hermes home paths, the external `gws` binary bridge, Contacts/Docs scopes we do not need |
| classcard extra (this repo) | Direct pattern | Optional-dependency packaging, lazy import with `*_EXTRA_NOT_INSTALLED` typed error, credentials in `~/.chat_lms_agent/`, static-registry + route-pack + memory-obligation registration | — |
| rclone/GAM-style embedded OAuth client | Adopt with override | Ship a default OAuth client id/secret for instant onboarding (installed-app secrets are not confidential per Google's own model); `--client-file` override for quota isolation | Shipping any *user* token or refresh token |

## Scopes (least privilege — fixed list)

| Scope | Why |
| --- | --- |
| `calendar.events` | Read/write lesson schedule events |
| `spreadsheets` | Create/append word-test and progress sheets |
| `drive.file` | Upload/manage **only files this app created** (test sheets) — never full Drive |
| `gmail.send` | Send mail only — no read access to the mailbox |

Requesting any scope outside this table is a failure condition.

## Must NOT Have

- No full-Drive or Gmail-read scopes; no Contacts/Docs until a real flow
  needs them (separate plan revision).
- No token, client secret, or OAuth code in the repo, in hydration context,
  in journals, or in memory entries (existing redaction patterns already
  cover `token`/`secret`; tests must pin this for the new files).
- No Gmail send without a consumable teacher approval (misaddressed mail to
  a parent is unrecoverable). Calendar/Sheets/Drive-file writes are
  additive and reversible on the teacher's own account: trace-journaled,
  no approval.
- No browser-automation fallback for Workspace tasks once this ships — the
  route pack and guard memory steer the agent to the CLI.
- Core harness stays dependency-free: all Google libraries live in the
  `[gws]` optional extra.

## Wave 0 — Owner decisions and prerequisites (no code)

- O0.1 The owner creates one OAuth client (Desktop type) in Google Cloud
  Console with the four scopes, and decides: embed it as the repo default
  (instant onboarding; shared quota) — recommended — with `--client-file`
  override documented for self-hosters.
- O0.2 Pin storage paths: token `~/.chat_lms_agent/google_token.json`,
  optional client override `~/.chat_lms_agent/google_client.json`
  (consistent with the classcard credential convention; outside repo and
  profile exports).
- O0.3 Register hermes-agent in `docs/oss-reference-registry.md`
  (reference-only, pinned SHA, must-not-copy: gateway/messaging machinery).

## Wave 1 — Core module, setup, packaging

- T1.1 Packaging: `[project.optional-dependencies] gws = [google-api-python-client,
  google-auth, google-auth-oauthlib]`; same libs in the dev group for type
  checking; vendored-style relaxations only if needed (prefer fully typed —
  this is new code, not vendored).
  - Red: `chat-lms gws status --json` without the extra →
    `GWS_EXTRA_NOT_INSTALLED` with the install hint (sys.modules block trick
    from the classcard gate test).
- T1.2 `gws_core.py`: token load/refresh/save (expiry-aware, refresh-token
  required-keys validation per the hermes reference), scope assertion
  (stored scopes ⊇ required scopes else `GWS_SCOPES_MISSING` with re-setup
  hint), lazy service builders for calendar/sheets/drive/gmail.
  - Red: refresh logic unit tests with synthetic token files (expired/
    missing-keys/wrong-scopes); no network in tests — refresh transport
    injected.
- T1.3 `chat-lms gws setup [--client-file <path>] --json`: opens the
  consent URL (headed browser via webbrowser.open; paste-code fallback for
  remote shells), writes the token file 0600-style, prints granted scopes.
  `chat-lms gws status --json`: token presence, expiry, scopes, account
  email (masked).
  - Red: status against synthetic token files (valid/expired/absent →
    PASS/NEEDS_REFRESH/NEEDS_SETUP); setup is live-only (not in CI).
- T1.4 Doctor row `gws`: NEEDS_SETUP (advisory, never UNSAFE) when the
  token is absent; PASS with scope list when valid.
  - Red: doctor payload contains the gws check with the right status per
    synthetic token state.

## Wave 2 — Primitive commands (one red/green per verb)

- T2.1 `gws calendar list --from <date> --to <date> --json` and
  `gws calendar create-event --title --start --end [--description] --json`.
  Trace-journaled. Times are ISO; timezone from the system.
- T2.2 `gws drive upload --file <path> [--folder-name <name>] --json` —
  `drive.file` scope means the app only ever sees its own uploads; returns
  file id + webViewLink.
- T2.3 `gws sheets create --title <t> --from-tsv <path> --json` and
  `gws sheets append --sheet-id <id> --from-tsv <path> --json` — TSV in,
  sheet out (the word-test format already produced by the wordbook/test
  flows).
- T2.4 `gws gmail send --to <addr> --subject <s> --body-file <path>
  [--attach <path>] --approval-id <id> --json` — requires an APPROVED,
  unconsumed approval (`ensure_approval_request` on first attempt →
  NEEDS_APPROVAL with the id; consume on send, exactly the academy-db
  import pattern). Recipient echoed in the approval operation text so the
  teacher approves a *specific* send.
  - All verbs: API errors mapped to typed codes (`GWS_AUTH_EXPIRED`,
    `GWS_API_ERROR` with status), never tracebacks.
  - Tests: service layer injected with fakes; CLI contract tests assert
    arg→call mapping, approval gating, and JSON shapes. No live API in CI.

## Wave 3 — Harness integration (the anti-amnesia layer)

- T3.1 Static registry entry `gws` (kind `external_api`, memory obligation
  `tool:gws`) advertising setup/status/calendar/drive/sheets/send commands.
  - Red: registry test + reuse-check matches "캘린더 일정" / "구글 시트".
- T3.2 Route packs (repo defaults): `routes/gws-calendar.json` (trigger:
  캘린더/일정 tokens → calendar list/create route, must_not: "do not
  automate a browser for calendar work"), `routes/gws-upload.json`
  (trigger: 시험지/시트/드라이브 업로드 → sheets/drive route, must_not:
  same browser ban + "gmail send requires teacher approval").
- T3.3 Onboarding: the onboarding skill gains a Google Workspace section
  (when to run `gws setup`, what the consent screen shows, where the badge
  lives); `bootstrap.ps1 -Mode User` prints the setup invitation after
  workspace creation (never blocks bootstrap on it); doctor NEEDS_SETUP
  closes the loop for teachers who skipped it.
- T3.4 Live profile memory `tool:gws` updated from the current guard note
  ("미설정 — browser-use로 대체 금지") to full usage after the teacher
  completes setup.

## Wave 4 — Composite teacher flows (after primitives prove out)

- T4.1 Word-test publish: one route that chains existing word-test TSV →
  `gws sheets create` (or `drive upload` for the HTML/docx artifact) →
  optional `gmail send` to the parent (approval-gated). Builds on the
  predecessor's `word_test_template`/`docx_email` assets — their migration
  is scoped here, classcard-style (Phase C of the predecessor migration).
- T4.2 Schedule sync assist: calendar list for the week surfaced in the
  side panel schedule view (read-only first).

## Development Method, Test Plan, Success And Failure Criteria

Method: wave order 0→1→2→3→4; red→green per task with captured evidence;
full gates (`pytest`, `ruff`, `basedpyright`) green at every commit; new
code fully typed (no vendored relaxations — this is fresh code).

Test plan: synthetic token files and injected fake services only; CI never
talks to Google; the live smoke is `gws status` + one `calendar list` on
the teacher's machine post-setup. Privacy suite extended: token filename
patterns asserted gitignored; hydration/journal outputs asserted free of
token material.

Success criteria: a fresh install reaches working Workspace commands with
exactly one browser consent during onboarding; "단어시험지 시트로 올려줘"
and "이번 주 일정 보여줘" route deterministically to gws commands (no
browser automation); gmail send is impossible without a teacher-approved,
single-use approval; removing the extra degrades every verb to the typed
install hint.

Failure criteria: any scope beyond the fixed four; token/secret text in
repo, context, journals, or memory; a send that bypasses the approval
ledger; core install gaining a Google dependency; the agent still reaching
for browser automation after Wave 3 lands.
