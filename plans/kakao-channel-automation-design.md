# KakaoTalk Channel Automation — Implementation Design

Detailed, chat-lms-shaped design for the free KakaoTalk path the owner
chose: drive the 채널 관리자센터 by headless browser (classcard reference),
no reseller, friends-only. Strategy lives in
`external-integrations-sms-kakao-plan.md`; this document is the *how*.

## Research findings (verified 2026-06-11)

- **Admin center** is `center-pf.kakao.com`, logged in with a 카카오계정.
- **Two free surfaces we automate:**
  - **메시지 (message)** — `채널 관리자센터 > 메시지 보내기`: full-broadcast to
    channel friends or to a friend-group built from phone numbers / app
    user ids. Basic text up to **400자**, plus one image/video and up to
    two buttons. This is the outbound path.
  - **1:1 채팅 (chat)** — inbound conversations from users who message the
    channel; supports saved replies and an away/auto-reply. This is the
    receive→track→summarize→reply path. **Access requires admin 2FA**
    (KakaoTalk or SMS), which is the main automation obstacle.
- **No official API** for either surface (the BizMessage API is
  reseller-only, separate). Automation is the only free route.
- **Free quota** is a monthly **PU credit** (free plan ≈ 10,000 PU/month of
  실비 across 알림톡/상담톡/문자), not "10,000 free messages." Channel
  friend-broadcast cost and the exact free ceiling must be **confirmed in a
  live calibration session** — the design treats the number as
  configuration, never a hard-coded assumption.
- **Reference: classcard** abstracts the page behind a `Protocol`
  (`open_main`/`ensure_logged_in`/…), runs a checkpointed sequence
  (`run_classcard_upload_sequence` + `resume_start_index`), and uses a
  persistent browser profile (one headed login, headless after). We copy
  this shape verbatim.

## Design principles (chat-lms fit)

1. **Protocol-first, browser-last.** A `KakaoChannelPage` Protocol defines
   the actions; the real Playwright implementation and a fake test double
   both satisfy it, so the entire sequence/checkpoint/approval logic is
   unit-tested with no browser (exactly how classcard tests run).
2. **Selectors are data, not code.** The admin center has no API contract
   and its DOM changes, so every selector lives in an externalized
   **calibration pack** (`routes/`-style JSON under the profile). Until a
   live calibration pins them, commands return `KAKAO_CALIBRATION_REQUIRED`
   instead of guessing — no brittle hard-coded selectors in the repo.
3. **Reuse the shared outward gate.** Friend-broadcast and chat-reply both
   reach humans → `third_party` → the `evaluate_outward_send` /
   `consume_outward_send` helper (Wave A), recipient-bound and single-use.
4. **Persistent profile + one headed login.** Login (incl. 2FA) happens
   once headed; the persistent profile keeps the session so later runs are
   headless. Session expiry returns a typed `KAKAO_LOGIN_REQUIRED`, never a
   silent failure.
5. **Paced, never parallel.** ToS-gray automation → human-pace delays, a
   per-run cap, serial execution, and an explicit per-instructor opt-in at
   setup. The risk register is surfaced in product copy and the route pack.
6. **Lazy Playwright, shared with classcard.** Reuse the existing
   `[classcard]` optional extra (Playwright) rather than a second one; lazy
   import so the core stays dependency-free; vendored-style lint scoping if
   needed.
7. **Free-quota awareness.** Track monthly sent volume in the profile DB
   and warn as the configured free ceiling approaches; suggest SMS fallback
   past it. The ceiling is calibration-set, not assumed.

## Module layout

| File | Responsibility |
| --- | --- |
| `kakao_login.py` | credentials path + 카카오계정 login flow (goto admin → if redirected to accounts.kakao.com, fill id/pw, handle 2FA prompt headed) |
| `kakao_channel_page.py` | `KakaoChannelPage` Protocol + the Playwright implementation that reads selectors from the calibration pack |
| `kakao_calibration.py` | load/validate the selector pack; `KAKAO_CALIBRATION_REQUIRED` when missing; capture helper used by `kakao calibrate` |
| `kakao_plan.py` | build a send plan (target friend group, message parts, image refs, per-run cap, pacing) — pure, fully testable |
| `kakao_send.py` | `run_kakao_send_sequence(plan, page, checkpoint, start_index)` — checkpointed, resumable (classcard shape) |
| `kakao_core.py` | 1:1 chat ingest → `kakao_messages` DB, per-contact threads, model summary, retrieval |
| `kakao_handlers.py` | CLI dispatch, lazy import, typed errors, JSON, approval gate wiring |

Secrets/profile: `~/.chat_lms_agent/kakao_credentials.json` and the
persistent `~/.chat_lms_agent/kakao-channel-profile/` (both gitignored,
asserted by the privacy suite). Calibration pack: profile-local JSON.

## CLI surface

- `kakao login [--headed]` — one-time headed login (+2FA); persists session.
- `kakao calibrate` — guided live session that captures/validates selectors
  into the calibration pack (the one unavoidable live step).
- `kakao send-friend --message <text|--body-file> [--image <path>]
  [--group <name>] --approval-id <id> [--max <n>] --json` — friend
  broadcast; **approval-gated**; checkpointed; echoes remaining free-quota
  estimate.
- `kakao chats pull --json` — ingest new 1:1 messages into the DB.
- `kakao chats reply --contact <id> --message <text> --approval-id <id>
  --json` — **approval-gated** in-session reply.
- `kakao summary --contact <id> --json` / `kakao history --contact <id>`.
- `kakao status --json` / doctor row — login state, calibration state,
  last-inbound timestamp, month-to-date volume vs ceiling.

## Handling the hard parts

- **2FA:** only at `kakao login`, headed; the human completes it; the
  persistent profile carries the session afterward. No attempt to automate
  the 2FA code itself.
- **Selector drift:** calibration pack + `kakao calibrate` re-run; commands
  fail typed (`KAKAO_CALIBRATION_REQUIRED`/`KAKAO_SELECTOR_MISSING`) rather
  than mis-click. A calibration carries a captured-at date surfaced by
  doctor so staleness is visible.
- **Free ceiling unknown:** stored as calibration config; volume tracked;
  warning + SMS-fallback suggestion near the limit. Never silently exceed.
- **ToS risk (distributed product):** opt-in per instructor, paced, serial,
  capped; product copy states the ban risk plainly; the route pack records
  that this is the free-but-fragile tier and SMS is the robust alternative.

## Test plan

- Fake `KakaoChannelPage` drives the full send sequence, checkpoint write,
  and `resume_start_index` with no browser (classcard-style).
- `kakao_plan` part-splitting, per-run cap, pacing — pure unit tests.
- Approval gate: friend-broadcast and chat-reply both blocked without an
  approved, recipient-bound, single-use approval.
- Calibration pack: missing → `KAKAO_CALIBRATION_REQUIRED`; malformed →
  typed error; valid → selectors resolve.
- `kakao_core`: ingest→DB→summary over seeded synthetic chats; no learner
  data in the repo.
- Quota tracker: warns at the configured threshold.
- Architecture test: the Kakao module imports no reseller/Solapi code.
- CI never touches KakaoTalk; the only live step is `kakao calibrate` on the
  instructor's machine.

## Success / failure criteria

Success: an instructor logs in once (headed, 2FA), calibrates once, then
sends approval-gated friend broadcasts and ingests/summarizes/replies to
1:1 chats headlessly; selectors live in a pack, not the code; quota is
tracked; everything degrades to typed errors, never silent failure or
mis-click.

Failure: hard-coded admin-center selectors in the repo; a send that bypasses
approval; automating the 2FA code; parallel/unpaced sending; assuming a free
ceiling; any KakaoTalk secret or profile in repo/context/journal/memory; a
new core runtime dependency.

## Waves (build order; each TDD, committed)

- **K0 — shared groundwork (already scaffolded):** the Wave A
  `integration_modules` framework + shared outward gate already exist
  (uncommitted); fold gws gmail onto the shared gate, land Wave A first.
- **K1 — Protocol + plan + checkpointed sequence:** `KakaoChannelPage`
  Protocol, `kakao_plan`, `run_kakao_send_sequence`, fake-driven tests. No
  browser, no CLI yet.
- **K2 — CLI + approval + quota:** `kakao_handlers`, `send-friend`/`status`,
  approval gate, quota tracker; subprocess contract tests.
- **K3 — Playwright implementation + calibration:** `kakao_login`,
  `kakao_channel_page`, `kakao_calibration`, `kakao calibrate`; live-only.
- **K4 — 1:1 chat ingest/summary:** `kakao_core`, `chats pull/reply`,
  `summary`.
- **K5 — harness registration:** static registry entry, `routes/kakao.json`
  (records the policy + risk facts), onboarding skill section, doctor row,
  `tool:kakao` memory obligation.

## Open questions to resolve in the calibration session (live, not now)

1. Exact admin-center URLs and DOM for compose/send and chat list/reply.
2. The real free-quota unit and ceiling for channel friend broadcasts.
3. Whether the persistent profile survives 2FA across days, or re-auth
   cadence — drives how often `kakao login` must re-run.
