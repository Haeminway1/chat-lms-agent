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
| Capability tier | official_api · official_cli · browser_automation · self_hosted | official_api (REST) | browser_automation | official_api (Solapi REST) | **self_hosted (chatbot + our tracker)** |
| Setup model | embedded_consent · per_user_account · per_user_channel · per_user_login | embedded_consent | per_user_login | **per_user_account + legal sender registration** | **per_user_channel + OBT approval (no business verification)** |
| Outward writes | none · self_account · third_party | self_account (cal/sheet/drive) + third_party (gmail) | third_party (uploads to classcard) | **third_party (SMS to a person)** | **third_party (in-session reply)** |
| Secret location | `~/.chat_lms_agent/<name>.json` always | google_token.json | classcard_credentials.json | solapi_credentials.json | **kakao_channel.json (no Solapi dependency)** |

> **Owner decisions (2026-06-11): Solapi-only for SMS · assisted per-user SMS
> setup · Kakao built self-hosted and free, NOT routed through Solapi.** The
> Kakao module is the openbuilder chatbot + our skill server (receive/save/
> track/summarize/reply) with zero per-message charge. Proactive Kakao push
> (알림톡) is reseller-mandated by Kakao policy and therefore deliberately
> out of the default scope — cold outreach uses SMS instead, so Solapi is
> never billed for Kakao.

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

3. **Kakao proactive push cannot be self-built — by Kakao policy, not by
   our choice.** Kakao does not expose a direct 알림톡/친구톡 API; sending
   is only possible through an official reseller (발송대행사/딜러사 such as
   Solapi, Aligo, NHN), which bills per message. There is no self-hosted
   path for cold outreach on KakaoTalk. **What IS fully self-built and
   free:** a 일반 채널 (individuals create it, no business verification) +
   a 카카오 i 오픈빌더 chatbot whose skill-server webhook we host. When a
   parent messages the channel, we receive → save → track → summarize →
   reply in-session, at zero per-message cost and with no Solapi
   dependency. **Design consequence (owner's call):** the Kakao module is
   the self-built inbound/response system; cold outreach to a parent uses
   SMS (already built in Wave B), so Solapi is never billed for Kakao. The
   reseller-routed 알림톡 path is recorded as an explicit optional add-on
   only, not the default — and it would still be Kakao-policy-gated, not
   something we can self-host around.

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

## Part 3 — KakaoTalk channel (Wave C): self-built, free, no Solapi

The whole module is the openbuilder chatbot + a skill server we host. No
reseller, no per-message charge, no business verification — a 일반 채널 an
individual creates is enough.

- C1 `kakao_skill_server.py`: a localhost HTTP server implementing the
  openbuilder skill contract; every inbound message is written to the
  profile DB (`kakao_messages`: channel, sender hash, text, media URLs,
  received_at) before any reply.
- C2 `kakao_core.py`: per-contact threads, model-generated rolling summary
  (stored), retrieval (`kakao history --contact`, `kakao summary
  --contact`), side-panel surfacing — our core strength over data we
  legitimately receive.
- C3 In-session reply through the open skill session (synchronous, plus
  openbuilder callback for the short async window); **third_party →
  approval-gated**. Inbound files captured as media URLs fetched to the
  profile store; outbound "files" sent as links (chatbot format limit,
  stated plainly).
- C4 Tunnel automation: detect/install cloudflared, raise a named tunnel
  to the skill server, write the public URL the teacher pastes into the
  openbuilder skill (the one paste OBT requires). `kakao doctor` checks
  server + tunnel + last-inbound timestamp.
- C5 Setup playbook (onboarding skill): agent-driven 일반 채널 creation +
  OBT application copy + skill URL wiring; the teacher only authenticates.
  Limits stated plainly: no proactive push (use SMS for cold outreach), no
  past-history import, ~6-day OBT, files-as-links.
- C6 Registration triple + routes/kakao.json. The route's must_not bans
  both browser automation of KakaoTalk and "sending 알림톡 by self-built
  means" (Kakao policy: reseller-only), steering cold outreach to SMS.
- Tests: skill-server request→DB→response contract with synthetic
  payloads; summary over seeded threads; reply approval gate; tunnel
  manager with a fake launcher. No live Kakao in CI; no Solapi import in
  the Kakao module (asserted by an architecture test).

### Optional appendix (not built now) — proactive 알림톡 via a reseller

If the owner later wants cold KakaoTalk outreach, it is **only** possible
through a reseller adapter (`messaging_providers/` gains a Kakao-capable
provider), requires a business channel + PFID + template approval, and
bills per message. Recorded for completeness; explicitly out of the
default build because SMS already covers cold outreach without it.

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

## Resolved decisions (2026-06-11)

- **SMS provider:** Solapi only (adapter protocol kept for future resellers).
- **SMS setup:** assisted `per_user_account` — agent automates all but the
  legal account + 발신번호 registration the teacher does once.
- **Kakao:** self-built and free — openbuilder chatbot + our skill server
  for receive/save/track/summarize/reply. NOT routed through Solapi, no
  business verification, no per-message charge. Cold outreach to parents
  uses SMS. Proactive 알림톡 (reseller-mandated by Kakao policy) is an
  explicit optional appendix, not built now.
- No remaining owner gate: every wave can proceed. (Wave C needs only the
  free 일반 채널 + OBT, which the agent walks the teacher through.)

## Sources

- Solapi single-message API — https://docs.solapi.com/api-reference/messages/sendsimplemessage
- Solapi API key / HMAC auth — https://developers.solapi.dev/references/authentication/api-key
- Solapi Kakao 알림톡/친구톡 guide — https://solapi.zendesk.com/hc/ko/articles/360022298993
- Solapi Kakao channel token (PFID) — https://docs.solapi.com/api-reference/kakao/requestplusfriendtoken
- Solapi pricing — https://solapi.com/pricing
- Aligo SMS API spec (reference) — https://smartsms.aligo.in/admin/api/spec.html
- Kakao business channel guide — https://kakaobusiness.gitbook.io/main/channel/start
- Kakao i Open Builder — https://i.kakao.com/
