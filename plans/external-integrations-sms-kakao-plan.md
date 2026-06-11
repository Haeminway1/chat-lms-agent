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
| Capability tier | official_api · official_cli · browser_automation · self_hosted | official_api (REST) | browser_automation | official_api (Solapi REST) | official_api (Solapi proactive) + official_api (chatbot inbound) + self_hosted (our tracker) |
| Setup model | embedded_consent · per_user_account · per_user_channel · per_user_login | embedded_consent | per_user_login | **per_user_account + legal sender registration** | **per_user_channel + business verification (proactive) / OBT approval (inbound)** |
| Outward writes | none · self_account · third_party | self_account (cal/sheet/drive) + third_party (gmail) | third_party (uploads to classcard) | **third_party (SMS to a person)** | **third_party (message to a person)** |
| Secret location | `~/.chat_lms_agent/<name>.json` always | google_token.json | classcard_credentials.json | solapi_credentials.json | solapi_credentials.json (proactive) + kakao_channel.json (inbound) |

> **Owner decisions (2026-06-11): Solapi-only · assisted per-user SMS setup ·
> full Kakao business path with maximal automation (user does only the legal
> identity verification).** This collapses SMS + Kakao proactive messaging
> onto a single Solapi account, since Solapi is an official Kakao
> 알림톡/친구톡 reseller.

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

1. **Solapi is the single account for both SMS and Kakao proactive.**
   Aligo is not actually cheaper (SMS 8.4 vs 8.0원, LMS 25 vs 14원, MMS 60
   vs 22원), so the owner chose Solapi-only. The upside: Solapi is an
   official Kakao 알림톡/친구톡 reseller, so one Solapi account (API key +
   secret, HMAC-SHA256 auth) sends SMS/LMS/MMS *and* — once a business
   channel is linked and a PFID is issued — 알림톡/친구톡. The provider
   protocol stays so other resellers can be added later, but Solapi is the
   only adapter built now.

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

3. **The Kakao path splits in two; the owner chose to do both.**
   - **Proactive (알림톡/친구톡 — message a parent first):** needs a
     비즈니스 채널 + 발신 프로필 키(PFID), routed through Solapi. Requires
     business verification, which in turn requires a 사업자등록번호. The
     owner accepts this and wants every registration step automated except
     the legally-personal identity verification (Toss benchmark).
   - **Inbound (receive → save → track → summarize → respond):** a
     카카오 i 오픈빌더 chatbot on the same channel, with a skill-server
     webhook. This is our tracking/summary strength over data we
     legitimately receive.

   **Hard prerequisite to surface:** the business channel + 알림톡 path
   requires the teacher to hold (or obtain) a 사업자등록번호. A private
   tutor without one can only run a 일반 채널 + chatbot (inbound + in-session
   reply), not proactive 알림톡. The agent can guide 사업자등록 but cannot
   perform the identity-bound act. This gate must be confirmed before the
   proactive half ships.

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

## Part 2 — Messaging via Solapi (Wave B)

One Solapi account drives SMS now and Kakao proactive later (Part 3).

- B1 `messaging_core.py` + `messaging_providers/solapi.py`: a
  `MessagingProvider` protocol (`send_text`, `send_kakao`, `balance`,
  `history`) with the Solapi adapter. Standard-library only — auth is an
  `Authorization: HMAC-SHA256 apiKey=…, date=…, salt=…, signature=…`
  header where `signature = HMAC-SHA256(date + salt, api_secret)` (built
  with `hmac`/`hashlib`/`secrets`); send is `POST
  https://api.solapi.com/messages/v4/send`. No SDK. The protocol stays so
  other resellers can be added, but Solapi is the only adapter now.
- B2 CLI:
  - `messaging setup` — capture API key/secret into
    `~/.chat_lms_agent/solapi_credentials.json` (0600), verify via a
    balance call, and list registered sender numbers.
  - `messaging status` — balance, registered senders, masked key, linked
    Kakao PFID (if any).
  - `sms send --to <num|학생명> --message <text|--body-file> [--image …]
    --approval-id <id>` — **third_party → approval-gated** (recipient +
    message digest bound into the approval); a dry-run flag avoids
    spending; recipients resolvable from the academy DB (parent phone).
  - `messaging balance` / `messaging history`.
- B3 Sender-registration assist: agent-driven flow that opens Solapi's
  발신번호 등록 page and lays out the document steps; the doctor row stays
  NEEDS_SETUP until at least one sender number is registered. The teacher
  performs only the identity-bound submission.
- B4 Registration triple + routes/sms.json (trigger 문자/SMS → sms send;
  must_not: browser automation; must_not: send without approval).
- Tests: Solapi adapter with injected transport (no network); the HMAC
  signature is computed against a known vector; approval gate before any
  send; DB recipient resolution; balance/preflight refusal at zero credit.
  CI never sends.

## Part 3 — KakaoTalk channel (Wave C): two halves, one channel

### C-proactive — 알림톡/친구톡 via Solapi (business path)

- CP1 Channel-link flow: `messaging kakao link` requests a PFID through
  Solapi (search-id + manager phone), after the teacher has a business
  channel. `kakao template register/list` manages 알림톡 templates
  (Kakao approval is asynchronous; status surfaced, never faked).
- CP2 `kakao send --to <학생명|num> --template <id|--friendtalk> …
  --approval-id <id>` — **third_party → approval-gated**, routed through
  the same Solapi adapter. Falls back to SMS when the recipient is not a
  channel friend (friend-talk requirement), stated in the result.
- CP3 Business-channel registration assist (Toss-benchmark): the agent
  drives the kakaobusiness channel creation + business-verification forms
  and prefills everything; the teacher performs only 본인인증 and supplies
  the 사업자등록번호. Doctor gates on PFID presence.

### C-inbound — receive/track/summarize/respond (chatbot, no business need)

- CI1 `kakao_skill_server.py`: a localhost HTTP server implementing the
  openbuilder skill contract; every inbound message is written to the
  profile DB (`kakao_messages`: channel, sender hash, text, media URLs,
  received_at) before any reply.
- CI2 `kakao_core.py`: per-contact threads, model-generated rolling
  summary (stored), retrieval (`kakao history --contact`,
  `kakao summary --contact`), side-panel surfacing — our core strength
  over legitimately received data.
- CI3 In-session reply through the open skill session; **approval-gated**.
  Inbound files captured as media URLs fetched to the profile store;
  outbound "files" sent as links (chatbot format limit, stated plainly).
- CI4 Tunnel automation: detect/install cloudflared, raise a named tunnel
  to the skill server, write the public URL the teacher pastes into the
  openbuilder skill (the one paste OBT requires). `kakao doctor` checks
  server + tunnel + last-inbound timestamp.
- CI5 Setup playbook (onboarding skill): agent-driven channel + OBT copy +
  skill URL wiring; limits stated plainly (no past-history import, ~6-day
  OBT, files-as-links).
- C6 Registration triple + routes/kakao.json (both halves).
- Tests: skill-server request→DB→response contract with synthetic
  payloads; summary over seeded threads; both send paths approval-gated;
  PFID link + template-status flows with injected transport; tunnel
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

## Resolved decisions (2026-06-11) and the one remaining gate

- **Provider:** Solapi only (adapter protocol kept for future resellers).
- **SMS setup:** assisted `per_user_account` — agent automates all but the
  legal account + 발신번호 registration the teacher does once.
- **Kakao:** full business path with maximal automation; the teacher
  performs only 본인인증 and provides the 사업자등록번호.
- **Remaining gate (blocks C-proactive only):** does the teacher hold a
  사업자등록번호? If yes, C-proactive proceeds. If no, the agent can guide
  사업자등록 (identity-bound; teacher submits), or C-inbound (chatbot)
  ships first independent of it. Wave A and Wave B (SMS) do not depend on
  this gate.

## Sources

- Solapi single-message API — https://docs.solapi.com/api-reference/messages/sendsimplemessage
- Solapi API key / HMAC auth — https://developers.solapi.dev/references/authentication/api-key
- Solapi Kakao 알림톡/친구톡 guide — https://solapi.zendesk.com/hc/ko/articles/360022298993
- Solapi Kakao channel token (PFID) — https://docs.solapi.com/api-reference/kakao/requestplusfriendtoken
- Solapi pricing — https://solapi.com/pricing
- Aligo SMS API spec (reference) — https://smartsms.aligo.in/admin/api/spec.html
- Kakao business channel guide — https://kakaobusiness.gitbook.io/main/channel/start
- Kakao i Open Builder — https://i.kakao.com/
