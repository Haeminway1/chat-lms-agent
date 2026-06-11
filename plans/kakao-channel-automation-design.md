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

- **K0 — shared groundwork — DONE (2026-06-11):** `integration_modules`
  framework + shared `evaluate_outward_send`/`consume_outward_send` gate;
  contract doc; 4-module descriptor table. Tested.
- **K1 — Protocol + plan + checkpointed sequence — DONE:**
  `KakaoChannelPage`/`KakaoChatPage` Protocols, `kakao_plan` (400-char
  chunking, run cap, pacing, button limits), `run_kakao_send_sequence`
  (checkpoint + resume), fake-driven tests. No browser.
- **K2 — CLI + approval — DONE:** `kakao_handlers`,
  `send-friend`/`status`/`chats`/`history`/`summary`/`login`/`calibrate`;
  every human-facing send routed through the approval gate; subprocess
  contract tests. (Quota *display* is stubbed — see K6.)
- **K4 — 1:1 chat ingest/summary — PARTIAL:** `kakao_core` ingest →
  per-contact JSON store → retrieval done; **summary is statistical**
  (counts + last message), not yet model-generated (see K6).
- **K5 — harness registration — DONE:** static registry entry
  (`tool:kakao`), `routes/kakao-channel.json` (approval + no-hardcoded-
  selectors + no-secrets must_not), doctor row, reuse-check aliases.

### Remaining

- **K3 — Playwright driver + live calibration — NOT STARTED (the real
  "hands"; blocks all actual sending).** Today `login`/`calibrate`/`chats
  pull`/`send-friend`(post-gate) return `KAKAO_LOGIN_REQUIRED` stubs. This
  wave cannot be written blind: the admin-center DOM is unknown and
  must-not-be-guessed (design rule). It requires a **live calibration
  session** (below). Deliverables once selectors are captured:
  `kakao_login.py` (headed 카카오계정 login + 2FA, persistent profile),
  the real `KakaoChannelPage`/`KakaoChatPage` Playwright implementations
  reading selectors from the pack, and `kakao calibrate` capture. Reuses
  the existing `[classcard]` Playwright extra (no new dependency).
- **K6 — polish (after K3 proves the shape):** model-generated rolling
  summary (replace the statistical stub); real quota tracking in
  `status`/doctor (month-to-date vs calibrated ceiling); inbound media
  fetch to the profile store.

## Live calibration session — what it is and who does what

K3 is not "use what's built"; it is the **discovery step that lets the
remaining driver code be written**. Selectors (`page.click("…")`) need the
exact admin-center DOM, which is private and changes — so we capture it
live rather than guess.

1. Agent launches the real 채널 관리자센터 in a headed browser on the
   teacher's machine.
2. **Teacher does only the identity-bound act:** 카카오 로그인 + 2FA. The
   persistent profile keeps the session afterward.
3. Agent walks the compose/send and 1:1 chat screens, captures the real
   selectors + the actual free-quota unit/ceiling into the calibration
   pack (`<profile-root>/.chat-lms-state/kakao/calibration.json`).
4. Agent implements `kakao_channel_page`/`kakao_login` against the captured
   selectors (TDD against the now-known DOM), behind the existing fakes.
5. A single real friend-broadcast and one 1:1 reply confirm the path
   end-to-end (approval-gated, paced).

Prerequisite the teacher provides before the session: a KakaoTalk **일반
채널** already created (free, no business verification) with at least one
test friend, and OBT for the chatbot half if 1:1 inbound is wanted now.

## Open questions resolved only in the live session

1. Exact admin-center URLs and DOM for compose/send and chat list/reply.
2. The real free-quota unit and ceiling for channel friend broadcasts.
3. Whether the persistent profile survives 2FA across days, or the re-auth
   cadence — drives how often `kakao login` must re-run.

## Handoff to the implementing agent (K3 + K6, cold-start)

State at handoff: skeleton committed (`782a9f2`); tree green
(`uv run pytest` 247 pass, `uv run ruff check`, `uv run basedpyright` all
clean). Everything below plugs into existing, already-tested seams — do not
redesign; fill the stubs.

**K3 — the only thing blocking real sending. Prerequisite: a live
calibration session (see runbook above) before this code can be correct;
do NOT guess selectors.**

- Create `kakao_login.py`: headed 카카오계정 login at `center-pf.kakao.com`
  (classcard's `login_classcard` in `classcard_direct_browser.py` is the
  reference shape), persistent profile at
  `~/.chat_lms_agent/kakao-channel-profile`, 2FA done by the human. Return a
  typed `KAKAO_LOGIN_REQUIRED` when the session is absent/expired.
- Implement the real `KakaoChannelPage`/`KakaoChatPage` (Protocols already
  in `kakao_channel_page.py`) as a Playwright class that reads selectors
  from the calibration pack (`kakao_calibration.load_calibration_pack`,
  `REQUIRED_SELECTORS`). The pure logic that consumes the page —
  `kakao_send.run_kakao_send_sequence` and the handler functions
  `kakao_handlers.send_friend_with_page` / `send_chat_reply(page=…)` — is
  done and fake-tested; just construct the real page and pass it in.
- Replace the stubs in `kakao_handlers.py` that currently return
  `_login_required_payload()`: `_send_friend` (after gate+calibration build
  the page and call `send_friend_with_page`), `_chats` `pull` (drive the
  chat list → `kakao_core.ingest_chat_history`), `_login`, `_calibrate`
  (real capture into the pack). Keep every human-facing send behind
  `evaluate_outward_send` (already wired) — never bypass it.
- Reuse the existing `[classcard]` Playwright extra; lazy-import Playwright
  inside the functions (classcard pattern) so the core stays import-clean.
- Privacy: the persistent profile, credentials, and calibration pack live
  only under the profile/user home — never commit them. `routes/
  kakao-channel.json` `must_not` already records this; keep it true.

**K6 — no live session needed, can start now:**

- Replace the statistical `kakao_core.summarize_chat_history` with a
  model-generated rolling summary (store it; keep counts as fallback).
- Wire real quota tracking into `kakao status` / the doctor `_kakao_check`
  (month-to-date sent vs the calibrated `free_quota_ceiling`).
- Fetch inbound media URLs to the profile store on `chats pull`.

**Gates & toolchain (every commit):** `uv run pytest`, `uv run ruff check`,
`uv run basedpyright` must stay green; TDD red→green per step; see
[[repo-toolchain-quirks]] (ruff/basedpyright concat conflict, cp949 console,
CRLF) and [[design-first-integrations]]. If `uv` fails on a broken `.venv`
(WinError 1920 on `lib64`), `rmdir /s /q .venv` then `uv sync`.

**Definition of done:** one real friend-broadcast and one 1:1 reply succeed
end-to-end on the teacher's machine, approval-gated and paced, with
selectors sourced only from the calibration pack.

## Execution plan — status as of 2026-06-11 QA and the live path

**Where we are.** K0/K1/K2/K4/K5 shipped and QA-passed (247 tests, ruff/
basedpyright clean): plan/sequence/checkpoint logic fake-page-verified,
both send paths approval-gated through the shared outward gate, selectors
externalized (zero in source — asserted), calibration pack loader with
typed errors, chat ingest/history/summary over a profile JSON store, and
the discovery triple (registry + route pack + doctor + reuse aliases).
**K3 — the real browser driver — is intentionally a stub** (`KAKAO_LOGIN_
REQUIRED`): the admin center has no API and no known DOM, so the driver
cannot be written until a live calibration captures real selectors.
Guessing selectors is a design violation, not a shortcut.

### Phase 1 — Land the skeleton (dev, now)

Commit the QA-passed skeleton exactly as reviewed. No behavior change.

### Phase 2 — Generic browser shell (dev, no selectors needed, ~1-2h)

What can be built without knowing the DOM:
- `kakao_login.py`: launch persistent context at
  `~/.chat_lms_agent/kakao-channel-profile`, open `center-pf.kakao.com`
  headed, wait for the teacher to finish 카카오계정 login + 2FA, verify the
  session landed (URL heuristic), report `login_state`. Mirrors
  `classcard_browser` launch options.
- `kakao calibrate` (real): open each admin surface headed, pause for the
  operator to confirm the on-screen element, snapshot cand
