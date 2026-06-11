# External Integration Modules — SMS (Aligo) and KakaoTalk Channel

## Purpose

Generalize the gws/classcard work into a first-class **External Integration
Module** concept, then add two new modules a teacher needs: SMS sending
(Aligo, with a swappable provider adapter) and a KakaoTalk channel
assistant (receive → save → track → summarize → respond). The guiding rule
the owner stated: *use the service's own API/CLI when one exists; build our
own adapter when it does not* — and keep setup as close to the Toss model
(user authenticates, everything else automatic) as each service legally
allows.

## The "외부 연동 모듈" abstraction (what gws + classcard already are)

A module is described by four axes. Naming them makes the differences
explicit and tells onboarding exactly how automatic setup can be.

| Axis | Values | gws | classcard | sms (aligo) | kakao |
| --- | --- | --- | --- | --- | --- |
| Capability tier | official_api · official_cli · browser_automation · self_hosted | official_api (REST) | browser_automation | official_api (REST) | official_api (chatbot) + self_hosted (our tracker) |
| Setup model | embedded_consent · per_user_account · per_user_channel · per_user_login | embedded_consent | per_user_login | **per_user_account + legal sender registration** | **per_user_channel + OBT approval** |
| Outward writes | none · self_account · third_party | self_account (cal/sheet/drive) + third_party (gmail) | third_party (uploads to classcard) | **third_party (SMS to a person)** | **third_party (reply to a person)** |
| Secret location | `~/.chat_lms_agent/<name>.json` always | google_token.json | classcard_credentials.json | aligo_credentials.json | kakao_channel.json |

Rules that fall out of the axes and apply to every module:

- **third_party writes are approval-gated** (consumable, recipient-bound),
  exactly like `gws gmail send`. SMS send and Kakao reply both qualify.
- **Secrets live only in the user home**, never in repo, hydration context,
  journals, or memory entries. Tests pin this.
- **Every module registers the triple**: static registry entry (kind +
  `tool:<id>` memory obligation), a route pack with a browser-automation
  ban for work data, and a doctor advisory row.
- **Setup model decides how "Toss-like" it can be.** Only
  `embedded_consent` (OAuth) reaches the pure one-consent experience.
  The others are honestly more than one step; the goal is to automate
  *every step the law and the vendor allow* and make the rest a guided,
  agent-driven flow (user clicks/authenticates, agent does the wiring).

This abstraction ships as `docs/external-integration-contract.md` plus an
`IntegrationModule` descriptor that gws/classcard adopt retroactively so
the doctor and registry render all modules uniformly.

## Hard truths from the research (these change scope — read first)

1. **Aligo is not dramatically cheaper than Solapi.** Observed list
   prices: SMS 8.4 vs 8.0원, LMS 25 vs 14원, MMS 60 vs 22원 — Solapi is
   equal-or-cheaper on every tier, and discounts on volume. The real
   savings lever in Korea is 알림톡 (Kakao alimtalk, ~6.5–9원 with far
   higher open rates), which needs business verification. **Design
   consequence:** do not hard-bind to Aligo. Build a provider adapter so
   the teacher picks the cheapest account they actually hold; ship Aligo
   and Solapi adapters first.

2. **SMS cannot be pure-Toss "embed once."** Korean law
   (전기통신사업법) requires every sender number to be pre-registered
   (발신번호 사전등록) by its owner, with documents (통신가입증명원 등).
   Each teacher must have their own provider account, their own API key,
   their own charged balance, and their own registered sender number.
   None of that is shareable/embeddable like an OAuth client. **The
   honest model is `per_user_account`:** the agent automates API-key
   capture, the send flow, balance/preflight checks, and *guides* the
   one-time number registration — but the teacher must complete the
   account + number registration themselves.

3. **Proactive KakaoTalk messaging needs business verification.** 알림톡/
   친구톡 (initiating a message to a user) require a 비즈니스 채널 +
   발신 프로필 키 + an official 딜러사 — exactly the hassle the owner wants
   to avoid. **What does NOT need business verification:** a 일반 채널
   (general channel, individuals can create it free) plus a 카카오 i
   오픈빌더 chatbot. When a user messages the channel, a skill-server
   webhook receives the text and the bot replies *within the
   conversation*. So "receive → save → track → summarize → respond" is
   achievable; "message a parent first, unprompted" is not (without
   business verification).

4. **Kakao chatbot has three real limits.** (a) It needs a public HTTPS
   endpoint → a tunnel (cloudflared/ngrok) for a Windows desktop, which we
   automate but which adds a moving part. (b) OBT approval (~6 days,
   email) gates go-live. (c) Inbound *files/images* arrive as limited
   media blocks, not arbitrary file ingestion; reliable capture is text +
   media URLs. Importing *past* conversation history is impossible — only
   messages after connection flow through. The plan states these in the
   product copy so no one expects more.

5. **KakaoTalk PC automation is a non-starter for distribution.** Driving
   the KakaoTalk desktop app to read a personal account violates Kakao's
   ToS and risks account ban; it is fragile across updates. We document it
   as explicitly rejected for the OSS product (unlike classcard, where
   browser automation of a site the user logs into is within bounds).

## Part 1 — The module framework (Wave A)

- A1 `integration_core.py`: the `IntegrationModule` descriptor (four axes
  above), a `capability_probe()` that reports configured/needs-setup, and
  a shared `outward_approval(plan_id, recipient, operation)` helper
  factored out of the gws gmail gate so SMS/Kakao reuse it verbatim.
- A2 Retrofit gws + classcard as descriptors; doctor and
  `agent-tools list` render every module through the same shape.
- A3 `docs/external-integration-contract.md` — the canonical rules; the
  privacy suite asserts no module writes secrets outside the user home.
- Red tests: descriptor round-trips; approval helper rejects a recipient
  mismatch; doctor lists all modules with correct setup_model.

## Part 2 — SMS via a provider adapter (Wave B)

- B1 `sms_core.py` + `sms_providers/`: a `SmsProvider` protocol
  (`send`, `balance`, `history`) with `aligo.py` and `solapi.py` adapters.
  Standard-library HTTP only (Aligo is `POST https://apis.aligo.in/send/`
  with `key`,`user_id`,`sender`,`receiver`,`msg`,`msg_type`,`title`,
  `image1-3`,`testmode_yn`; plus `/remain/`,`/list/`,`/cancel/`). No SDK.
- B2 CLI:
  - `sms setup --provider aligo` — capture API key/user_id into
    `~/.chat_lms_agent/aligo_credentials.json` (0600), verify via
    `/remain/`, and print the registered sender numbers it can see.
  - `sms status` — provider, balance, registered senders, masked key.
  - `sms send --to <num|학생명> --message <text|--body-file> [--image ...]
    --approval-id <id>` — **third_party → approval-gated** (recipient and
    a message digest bound into the approval), `testmode_yn` honored for
    dry runs, recipients resolvable from the academy DB (parent phone).
  - `sms balance` / `sms history`.
- B3 Sender-registration assist: a guided flow that opens the provider's
  number-registration page and lays out the document steps; doctor row
  stays NEEDS_SETUP until at least one sender number is registered.
- B4 Registration triple + routes/sms.json (trigger 문자/SMS → sms send,
  must_not: browser automation, must_not: send without approval).
- Tests: provider adapters with injected transport (no network);
  `testmode_yn` path; approval gate before any send; DB recipient
  resolution; balance/preflight refusal when points are zero. CI never
  sends.

## Part 3 — KakaoTalk channel assistant (Wave C)

The legitimate, no-business-verification path: 일반 채널 + 오픈빌더 chatbot
+ a local skill server the CLI runs, exposed through an automated tunnel.

- C1 `kakao_skill_server.py`: a localhost HTTP server implementing the
  openbuilder skill contract (receive the user utterance + media URLs,
  return a skill response). Every inbound message is written to the
  profile DB (`kakao_messages`: channel, sender hash, text, media URLs,
  received_at) before any reply.
- C2 `kakao_core.py` conversation layer: per-contact threads, rolling
  summary (model-generated, stored), retrieval (`kakao history --contact`,
  `kakao summary --contact`), and side-panel surfacing. This is our own
  code over data we legitimately receive — the owner's core ask.
- C3 Reply path: `kakao reply --contact <id> --message <text>` returns
  through the open skill session; **third_party → approval-gated**.
  Inbound files captured as media URLs fetched to the profile store;
  outbound "files" sent as links (chatbot format limit, stated plainly).
- C4 Tunnel automation: detect/install cloudflared, bring up a named
  tunnel to the skill server, and write the public URL the teacher pastes
  into the openbuilder skill (the one manual paste OBT requires). `kakao
  doctor` checks server + tunnel + last-inbound timestamp.
- C5 Setup playbook (onboarding skill): agent-driven channel creation +
  OBT application copy + skill URL wiring; user authenticates/clicks, the
  agent does the rest. Clear statement of limits (no proactive send, ~6-day
  OBT, no history import, files-as-links).
- C6 Registration triple + routes/kakao.json.
- Tests: skill-server request→DB→response contract with synthetic
  payloads; summary layer over seeded threads; reply approval gate; tunnel
  manager with a fake launcher. No live Kakao in CI.

## Development method, test plan, success/failure criteria

Method: Wave A → B → C; red→green per task; full gates (pytest, ruff,
basedpyright) green at every commit; standard-library HTTP only (no new
runtime deps in core); secrets only in user home.

Test plan: injected transports / fake servers throughout; CI never reaches
Aligo, Solapi, or Kakao; Aligo `testmode_yn=Y` is the only "live-shaped"
path and remains opt-in/manual. Privacy suite extended: credential
filenames gitignored; hydration/journal/memory asserted free of API keys,
sender numbers, and message bodies.

Success criteria: a teacher can (1) configure an SMS provider and send an
approval-gated SMS resolved from a student's parent number, swapping
providers by a flag; (2) stand up a Kakao channel assistant that saves,
threads, and summarizes inbound messages and replies under approval —
without business verification; (3) every module appears in the registry,
reuse-check, doctor, and a browser-banning route pack, so a fresh session
never improvises with browser automation.

Failure criteria: any secret in repo/context/journal/memory; a third_party
send (SMS or Kakao reply) that bypasses approval; a new core runtime
dependency; the product depending on KakaoTalk PC automation; onboarding
copy that implies proactive Kakao messaging or past-history import works
without business verification.

## Open decisions (owner must choose before Wave B/C)

1. **SMS provider scope** — ship Aligo + Solapi adapters (recommended,
   since Aligo is not actually cheaper), or Aligo only?
2. **SMS setup honesty** — accept the `per_user_account` model (agent
   automates everything except the legally-required account + sender
   registration the teacher does once), since pure-Toss is not legal for
   SMS?
3. **Kakao path** — the legitimate chatbot route (receive/track/summarize/
   reply, no proactive send, needs a tunnel + ~6-day OBT) — confirm this is
   the intended scope, with proactive 친구톡 deferred to a future
   business-verification track?

## Sources

- Aligo SMS API spec — https://smartsms.aligo.in/admin/api/spec.html
- Solapi pricing — https://solapi.com/pricing
- Kakao business channel guide — https://kakaobusiness.gitbook.io/main/channel/start
- Kakao Developers webhook/callback — https://developers.kakao.com/docs/latest/ko/kakaotalk-channel/callback
- Kakao i Open Builder — https://i.kakao.com/
