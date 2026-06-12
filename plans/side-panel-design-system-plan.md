# Side Panel Design System Plan (open-design + Toss-style + anti-hardcoding)

Status: QUEUED — execute AFTER `plans/prompt-intent-routing-and-lesson-panel-plan.md`
(all four waves + final QA). Wave D3/D4 depend on the lesson runtime,
`install-assets`, and doctor rows that plan delivers.
Author: investigation session 2026-06-12.
Executor: implementing agent works ONE wave at a time (D1→D4).

## Purpose

Three user-reported defects in today's side-panel reality:

1. **Visual quality** — rendered panels look bad and drift from the documented
   design reference (372×760 narrow shell, Toss-blue `#3182F6`, Pretendard
   typography are already specified in
   `docs/side-panel-design-reference.md` but nothing enforces them).
2. **Spec non-compliance** — there is no machine-checkable display spec, so
   artifacts violate layout rules (horizontal scroll, wrong shell size).
3. **Hardcoded data** — viewers sometimes ship with data typed directly into
   the HTML instead of fetching from the local read-only API. Nothing detects
   this today.

Target architecture: a **per-user design factory with deterministic gates**.
Design *generation* is intentionally non-deterministic and per-user (each of
100 users can generate their own look, with their own brief, on their own
Codex login). Design *acceptance* is deterministic: a display-spec lint, a
data-binding verifier, and the existing draft→approve→promote block lifecycle
decide what goes live. Defaults ship as data (Toss-style design system), and
[nexu-io/open-design](https://github.com/nexu-io/open-design) plugs in as an
optional richer generation engine, with the plain Codex CLI (user's existing
ChatGPT OAuth) as the zero-setup default engine.
[pbakaus/impeccable](https://github.com/pbakaus/impeccable) joins as the
anti-slop quality layer: its deterministic detector rules run against every
draft when the tool is installed, and the findings drive one bounded
refinement pass before human review.

## User Requirements (verbatim mapping)

- open-design 연동 가능 + 기본은 Codex CLI OAuth로 디자인 → DS5 (two engine
  adapters; codex default, open-design optional).
- 디자인 규격 2가지, 유동적이되 제한 — codex 앱 내 side panel: 화면분할/모바일
  느낌, 가로 스크롤 금지; 전체화면 규격; 한 artifact가 둘 다 지원하면 우대 →
  DS1/DS2 (display-spec-v1 `panel` + `fullscreen` modes, panel mandatory).
- 기본 디자인은 토스식 → DS4 (Toss-style design system as repo default data).
- DB 연동 없이 직접 기입 금지 → DS3 (dual-fixture data-binding verifier).
- deterministic 아님 + 모든 사용자 맞춤 → generation is per-user and creative;
  only the GATES are deterministic. Per-profile design systems/briefs/tokens,
  same profile-wins precedence as route packs.
- impeccable 추가 사용 (2026-06-12 follow-up) → DS2/DS5: detector pass on
  every draft + findings-driven refinement iteration; advisory, never a
  hard dependency.

## Verified Current State (2026-06-12)

- Contract exists, enforcement does not: `docs/side-panel-design-reference.md`
  pins shell 372×760, accent `#3182F6`, Pretendard, warning-first, registered
  sections; `src/chat_lms_agent/side_panel.py` pins `VIEWS`, `SECTION_TYPES`,
  `BLOCK_CATALOG`, `TOKEN_AXES` (accent default `#3182F6`, density/round/
  theme/fontSize axes). Nothing validates an actual HTML artifact against any
  of it.
- `src/chat_lms_agent/side_panel_validation.py` validates **payload JSON**
  only (sections, source_commands provenance, design_tokens, action approval
  flags). `synthetic: true` marks sample payloads; production payloads
  require `source_commands`. There is no HTML-level check and no proof that a
  viewer actually *binds* payload data (a viewer with hardcoded numbers
  passes everything today).
- Block lifecycle machinery already exists and must be reused, not
  reinvented: `side_panel_blocks.py` + handlers expose
  scaffold/register/promote/deprecate/preview/explain with quarantine,
  teacher approval, and evidence (V5). `docs/golden-standards.md` (gajae-code
  entry) already states the rule: generated artifacts are drafts until
  tests, review, and evidence promote them.
- After the routing plan lands: repo ships `assets/side-panel/` lesson
  viewer/server templates, `side-panel lesson install-assets`, doctor asset
  rows. This plan upgrades that template and gates future generated
  replacements.
- External reference (fetched 2026-06-12): **nexu-io/open-design** —
  Apache-2.0, local-first daemon (127.0.0.1) + `od` CLI + MCP server + REST;
  spawns 22+ coding-agent CLIs **including Codex** (auth = the CLI tool's own
  credentials, i.e. the user's ChatGPT OAuth — no API key needed); design
  systems are `DESIGN.md` data files (9-section schema: color, typography,
  spacing, components, motion, voice, anti-patterns…); artifacts are
  single-page HTML rendered in sandboxed iframes. Integration points: `od`
  CLI, REST (`/api/skills`, `/api/design-systems`, …), MCP, plugin manifest.
- External reference (fetched 2026-06-12): **pbakaus/impeccable** —
  Apache-2.0 "design language for AI coding agents" targeting repetitive
  AI-slop design. Ships 41 **deterministic** anti-pattern detector rules
  (overused fonts, gray-on-color text, excessive card nesting, bounce
  easing, purple-blue gradients, poor spacing/touch targets/heading
  hierarchy) runnable WITHOUT model calls via
  `npx impeccable detect [--fast] --json` against directories, HTML files,
  or URLs; plus a cross-harness skill (`npx impeccable skills install`,
  Codex CLI supported) exposing `/impeccable audit|polish|critique|…`
  commands; plus an `init` convention generating `PRODUCT.md`/`DESIGN.md`
  context files — the same design-context-as-data philosophy as
  open-design and this repo.

## External Golden Standards (register per repo convention)

Add to `docs/golden-standards.md` + `docs/oss-reference-registry.md`
(pin head SHA at implementation time; license fields below verified):

| Reference | Adopted trait | Must NOT copy |
| --- | --- | --- |
| `open-design` (nexu-io, Apache-2.0) | design-systems-as-data (`DESIGN.md` 9-section schema); engine-adapter contract (one entry per agent CLI); draft artifact + sandboxed preview separation; local-first 127.0.0.1 boundary | daemon/marketplace/model-router internals; unified billing; any always-on network service |
| `impeccable` (pbakaus, Apache-2.0) | deterministic anti-pattern detectors as an external quality gate (`npx impeccable detect --json`, version-pinned); detector findings → one bounded refinement iteration; `PRODUCT.md`/`DESIGN.md` context convention kept compatible | re-implementing or vendoring its 41 rules in-repo; making its advisory verdict a hard gate on machines where the tool is absent; any of its LLM-critique modes inside CI |
| Toss design language (public guidelines; proprietary) | design PRINCIPLES as authored data: one accent, generous whitespace, clear hierarchy, mobile-first single column, motion restraint — written into our own `DESIGN.md` | any proprietary TDS assets, fonts, icons, copy, or CSS; no scraping TDS packages |
| Pretendard (SIL OFL 1.1) | font-stack convention `Pretendard Variable, Pretendard, -apple-system, …` with system fallback | bundling font binaries into the repo (reference by local install / system fallback only — artifacts must render offline without it) |
| (reuse) gajae-code + OMX entries | draft→evidence→promote lifecycle; machine-readable verdicts before narrative | already registered |

## Design Decisions

- **DS1 — display-spec-v1 as data.** New repo file
  `assets/side-panel/display-spec-v1.json` defining two mode profiles:
  - `panel`: base viewport 372×760, width band 360–480, single column,
    `horizontal_scroll: "forbidden"`, vertical scroll allowed, touch targets
    ≥ 44px, font size per `TOKEN_AXES` (13–18).
  - `fullscreen`: viewport ≥ 1024×768, multi-column allowed, horizontal
    scroll still forbidden at the document level.
  Every artifact declares its modes via `<meta name="side-panel-modes"
  content="panel">` or `"panel fullscreen"`. `panel` support is MANDATORY;
  `fullscreen` is recommended; one responsive artifact serving both is the
  preferred form. The spec file is contract data (NOT per-user overridable);
  per-user freedom lives in design systems/tokens/briefs (DS4/DS5).
- **DS2 — deterministic static lint.** New CLI
  `side-panel design lint --artifact <html> [--mode panel|fullscreen|all]
  --json` (module `side_panel_design_lint.py`, stdlib only): checks
  viewport meta present; modes meta present and includes `panel`; no
  `overflow-x: auto|scroll` on `html`/`body`/shell containers; no fixed
  `width` declarations exceeding the active mode's band on top-level
  containers; theme implemented via CSS custom properties for every
  `TOKEN_AXES` axis; Pretendard-first font stack with system fallback; fully
  offline single file (no external `http(s)://` src/href/`@import`; no CDN);
  a `fetch(` call targeting a relative `/api/` path exists; light AND dark
  theme blocks present. Exit/error-list contract mirrors
  `side_panel_validation.py`. Lint is pure text/CSS analysis — fast,
  dependency-free, runs everywhere.
  **Impeccable advisory layer:** when `npx impeccable detect` is available
  locally, lint additionally runs it (version-pinned invocation,
  `--fast --json`, offline detector rules only) and attaches its findings
  under an `advisory.impeccable` key; tool absent → `advisory.impeccable =
  {"status": "SKIPPED", "reason": "impeccable not installed", "install_hint":
  "npx impeccable skills install"}`. Our own display-spec verdict stays
  self-contained and deterministic on every machine; impeccable findings are
  surfaced to the teacher at approval time and recorded in evidence, but do
  not flip lint's PASS/FAIL by default.
- **DS3 — dual-fixture data-binding verifier (anti-hardcoding).** New CLI
  `side-panel design verify --artifact <html> --view <view> [--mode …]
  --json`: builds two deterministic synthetic payloads A and B for the view
  (distinct marker strings per section, `synthetic: true`), serves them from
  an ephemeral 127.0.0.1 server implementing the view's `/api/...` shape,
  renders the artifact headlessly (Playwright chromium — already in the dev
  dependency group), and asserts: (a) fixture-A markers appear in the DOM;
  (b) re-render against fixture B shows B's markers and NOT A's (proves live
  binding — hardcoded data fails here); (c) `panel` mode at 372×760:
  `scrollingElement.scrollWidth <= clientWidth` (no horizontal scroll);
  (d) `fullscreen` mode (if declared) at 1440×900: same horizontal-scroll
  assertion. Playwright or its browser missing → `BLOCKED` +
  `error_code: "DESIGN_VERIFY_RUNTIME_MISSING"` + install hint (never
  auto-download). Verify emits an evidence JSON (artifact sha256, spec
  version, per-check verdicts, timestamp) for DS6.
- **DS4 — Toss-style default design system as data.** Repo ships
  `assets/design-systems/toss-style/DESIGN.md` (adopting open-design's
  9-section schema so the same file drives BOTH engines) + `tokens.json`
  aligned with `TOKEN_AXES` (accent `#3182F6`, Pretendard stack, spacing/
  radius/elevation scales, motion restraint, voice: 친절한 존댓말, explicit
  anti-patterns: no horizontal carousels, no dense tables in panel mode, no
  decorative gradients). Per-user customization: profile dir
  `<profile-root>/.chat-lms-state/design-systems/<id>/DESIGN.md` adds or
  overrides by id — same first-wins/profile-wins pattern as route packs.
  New CLI `side-panel design systems list --json` (id, source repo|profile,
  summary).
- **DS5 — generation engines behind one CLI, non-deterministic by design.**
  New CLI `side-panel design generate --view <view>
  [--modes panel|panel,fullscreen] [--design-system <id>] [--brief <text>]
  [--engine codex|open-design] --profile-root <root> --json`.
  Composes one generation context: DESIGN.md + display-spec + the view's
  payload JSON schema + a synthetic fixture payload + hard constraints
  (single offline HTML file, fetch from relative `/api/`, registered blocks
  only, declare modes meta, both themes). Engines:
  - `codex` (DEFAULT — zero extra setup): spawn `codex exec` with the
    composed context; uses the user's existing Codex CLI ChatGPT OAuth.
  - `open-design` (optional): probe local daemon/`od` CLI; submit the same
    context as a brief via `od`/REST; daemon absent → `BLOCKED` +
    `error_code: "OPEN_DESIGN_NOT_INSTALLED"` + pinned install hint. Never
    auto-install, never call non-local endpoints.
  Engine output NEVER goes live directly: it lands as a DRAFT artifact in
  profile quarantine via the existing block/asset lifecycle, lint (DS2) and
  verify (DS3) run automatically, and the JSON result reports verdicts +
  preview path. Engine adapters live behind a small interface so tests use a
  deterministic FAKE engine (records the composed context, emits a fixture
  artifact) — no real model calls in CI.
  **Bounded refinement loop:** after a draft lands, run our lint plus the
  impeccable detector (when installed); if findings exist, re-prompt the SAME
  engine exactly once with the machine-readable findings list appended
  ("fix these detector findings, change nothing else"), then re-run the
  checks. One iteration maximum — no unbounded polish loops. Both rounds'
  findings are kept in the draft's evidence trail. The generation context
  also names the impeccable anti-pattern categories (anti-slop guidance) and
  stays compatible with its `PRODUCT.md`/`DESIGN.md` convention so users who
  installed the impeccable skill into their Codex CLI get consistent
  behavior in interactive sessions (`/impeccable polish` documented as an
  optional manual follow-up).
- **DS6 — promotion gate + retrofit.** Promote (existing lifecycle verb,
  teacher-approval-gated) requires lint PASS + verify PASS evidence recorded
  against the artifact's sha256; promoting installs the artifact as the
  profile's viewer for that view (timestamped backup of the previous file;
  deprecate restores). Doctor gains rows: installed viewers' lint status and
  verify-evidence age; missing/stale evidence → repair action `side-panel
  design verify …`. The repo's default lesson viewer template (from the
  routing plan's Wave 3) is upgraded in this plan to pass lint for BOTH
  modes with Toss-style tokens — out-of-the-box compliance, no generation
  required for the default experience.

### Non-goals

- No bundling or vendoring of open-design or impeccable (external optional
  tools; pinned references only). No auto-install of anything. Impeccable's
  advisory verdict never hard-blocks on machines where it is absent.
- No React/build toolchains in artifacts — single-file offline HTML only.
- No proprietary Toss assets; principles are authored in our own words.
- No font binaries in the repo (OFL referenced, system fallback mandatory).
- No automatic regeneration or replacement of a user's promoted viewer
  without explicit teacher approval.
- Generation QUALITY is not gate-tested (taste is the user's); only contract
  compliance (spec/binding/themes/offline) is enforced.
- No network calls in tests; no real engine calls in CI (fake engine only).

## Wave D1 — Display spec + static lint

- [x] RED: lint truth-table tests over fixture HTMLs: compliant
      panel-only artifact PASS; horizontal-scroll style FAIL; fixed
      width 720px in panel mode FAIL; missing modes meta FAIL; external CDN
      stylesheet FAIL; missing `/api/` fetch FAIL; missing dark theme FAIL;
      fullscreen-declared artifact checked against fullscreen rules.
- [x] RED: spec file schema test (`display-spec-v1.json` parses, both modes
      present, values match `docs/side-panel-design-reference.md`).
- [x] GREEN: implement DS1 spec file + DS2 `side_panel_design_lint.py` +
      `side-panel design lint` CLI wiring + `docs/` spec section.
- [x] Doctor row (static): installed profile viewers lint status (reuse the
      asset discovery from the routing plan's doctor work).
- [x] GATE: `uv run ruff check` && `uv run basedpyright` &&
      `uv run pytest -q`; commit.

## Wave D2 — Toss-style design system as data + registry

- [x] RED: design-system resolution tests (repo default visible; profile
      override by id wins; malformed DESIGN.md skipped with warning —
      mirror route-pack loader semantics); `systems list` CLI contract test.
- [x] GREEN: `assets/design-systems/toss-style/DESIGN.md` + `tokens.json`
      (9-section schema, values from DS4) + resolver module + CLI.
- [x] Docs: add the four golden-standard entries
      (`docs/golden-standards.md`) + registry JSON entries with pinned SHAs
      (`docs/oss-reference-registry.md`), impeccable included.
- [x] RED+GREEN: impeccable advisory integration in lint — detector present
      (fake the subprocess in tests) → findings under `advisory.impeccable`;
      absent → typed SKIPPED with install hint; lint PASS/FAIL unaffected
      either way.
- [x] GATE: gates green; commit.

## Wave D3 — Generation engines + quarantine wiring

- [x] RED: fake-engine tests: `design generate` composes context containing
      DESIGN.md content, display-spec, view schema, synthetic fixture, and
      hard constraints; draft lands in quarantine (NOT installed); lint runs
      automatically and verdict appears in output; two different profiles
      with different design systems produce independently stored drafts with
      no repo writes.
- [x] RED: engine selection tests: default engine is `codex`; `--engine
      open-design` without a local daemon → `BLOCKED` /
      `OPEN_DESIGN_NOT_INSTALLED`; codex CLI missing from PATH → `BLOCKED` /
      `CODEX_CLI_NOT_FOUND` with auth-free hint text.
- [x] RED: refinement-loop tests with the fake engine: findings on round 1 →
      exactly one re-prompt containing the findings list → checks re-run;
      zero findings → no second round; loop never exceeds one iteration.
- [x] GREEN: engine adapter interface + codex adapter (subprocess `codex
      exec`, composed prompt, artifact extraction) + open-design adapter
      (probe + submit; live path manually smoke-tested, not CI-tested) +
      impeccable-findings refinement pass + quarantine/lifecycle wiring.
- [x] GATE: gates green; commit.

## Wave D4 — Binding verifier + promotion gate + template retrofit

- [ ] RED: verifier tests with a local fixture artifact: data-bound artifact
      PASS (A markers, then B markers after fixture swap); deliberately
      hardcoded-data artifact FAIL (B markers absent); horizontal-scroll
      artifact FAIL in panel mode; playwright-missing path returns
      `DESIGN_VERIFY_RUNTIME_MISSING` (simulate via env guard). Mark
      browser-dependent tests with a skip-if-no-chromium guard so CI without
      installed browsers stays green.
- [ ] RED: promotion gate tests: promote without verify evidence → blocked
      with the existing lifecycle error semantics; with lint+verify evidence
      → installs viewer with timestamped backup; deprecate restores.
- [ ] GREEN: DS3 verifier + evidence JSON + DS6 promote/doctor wiring.
- [ ] Retrofit: upgrade the repo lesson viewer template to pass `design lint`
      for panel AND fullscreen with Toss-style tokens; add that lint run to
      its existing template tests.
- [ ] Docs: `docs/side-panel-design-reference.md` gains the two-mode spec
      table; `plans/STATUS.md` entry; follow-up note: move
      `WEAK_ROUTE_CATALOG_SIGNALS` (routing plan) into data alongside design
      systems if catalog tuning becomes per-user.
- [ ] GATE: gates green; commit.

## Acceptance (end to end, tmp profile, after D4)

1. `side-panel design lint --artifact <repo lesson template>` → PASS for
   panel and fullscreen (OOTB compliance).
2. A fixture artifact with hardcoded learner-looking data → lint may PASS
   but `design verify` FAILS on the fixture-swap check (anti-hardcoding
   proven by regression test).
3. An artifact with horizontal scroll at 372×760 → FAIL (panel mode).
4. Fake-engine `design generate` on two profiles with different
   design-system ids → two distinct quarantined drafts; neither installed;
   promote blocked until evidence exists; promote with evidence installs +
   backup.
5. `--engine open-design` without daemon → actionable BLOCKED JSON; with
   daemon (manual smoke, documented transcript in `evidence/`, local only)
   → draft artifact arrives through the same quarantine path.
5b. impeccable installed → draft evidence contains `advisory.impeccable`
   findings from both refinement rounds; not installed → typed SKIPPED
   marker and an otherwise identical flow (proven by the fake-subprocess
   tests).
6. All gates green on Windows; Linux suite (`--ignore` bootstrap files)
   green; no new runtime dependencies (playwright stays dev/optional).

## Failure criteria

- Any gate red; any existing side-panel/wordbook/routing test weakened.
- Lint or verify returns false-PASS on the negative fixtures above.
- Generated artifacts written anywhere outside profile quarantine before
  promotion, or installed without teacher approval.
- Any test or default path performing network access or real model calls.

## Execution Protocol (binding)

Identical to `plans/prompt-intent-routing-and-lesson-panel-plan.md`
Execution Protocol (TDD, gates before every commit, hermetic conftest,
ISC003/NUL traps, public-safety: `가상학생` only, no machine paths), plus:

- Playwright usage stays inside the dev dependency group; verify must
  degrade to a typed BLOCKED payload, never a stack trace, when the browser
  runtime is absent.
- The fake engine is the only engine exercised by pytest; real codex /
  open-design invocations are manual smokes with transcripts under
  `evidence/` (local only, never committed).
- Apache-2.0 attribution for any adopted open-design schema text; SIL OFL
  note for the Pretendard stack reference.
