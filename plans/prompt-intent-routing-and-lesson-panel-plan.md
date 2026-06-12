# Prompt Intent Routing and Lesson Panel Plan

Status: READY FOR IMPLEMENTATION (wave-gated, sequential)
Author: investigation session 2026-06-12 (validated live, line-level evidence below)
Executor: implementing agent works ONE wave at a time; never start wave N+1
inside a wave-N run.

## Purpose

Cold-start sessions cannot route natural lesson-prep requests. A teacher says
`학원 수업 뷰어 열어줘`, `수업준비 해줘`, or `수업 보조패널 열어줘` and the
harness answers `NO_MATCH` / `manual_review_required`, after which the agent
improvises (typically hand-writing a fresh HTML report — explicitly the
behavior the product forbids). This plan makes the pipeline
`natural language → deterministic route OR injected intent catalog → fixed CLI
→ fixed viewer fed by a local read-only JSON API` real, in four waves:

1. **Wave 1** — one matching engine for hook and `prompt-check`; alias-capable
   route packs (`route-pack-v2` with `any_tokens`).
2. **Wave 2** — `side-panel lesson` CLI surface + `lesson_assistant_panel`
   route pack + NO_MATCH intent catalog injection + route-use telemetry.
3. **Wave 3** — lesson panel runtime: payload builder in the package, fixed
   viewer HTML + stdlib server templates shipped in repo, `install-assets`.
4. **Wave 4** — asset guarantees (bootstrap materialization, doctor rows),
   private-workspace hydrate wording fix, docs.

## Verified Current State (line-level evidence, 2026-06-12)

All confirmed in the working tree and by live smoke runs this session.

- `src/chat_lms_agent/prompt_routes.py:17` — built-in route requires a
  wordbook token (`단어/단어장/wordbook/vocabulary`) AND a workflow token
  (`:18-32`). `학원 수업 뷰어 열어줘`, `수업준비 해줘`,
  `수업 보조패널 열어줘` all return `NO_MATCH` (reproduced).
- **Two divergent routing engines.** The UserPromptSubmit hook checks the
  built-in route, then route packs (`src/chat_lms_agent/commands.py:243-252`).
  `agent-tools prompt-check` (`prompt_routes.py:129-172`) never loads route
  packs. Live-proven: with a profile pack whose token matches
  `수업준비 해줘`, the hook injects `prompt_route` but `prompt-check` still
  returns `NO_MATCH`. The "mandatory gate" the agent is told to run first is
  blind to the data-driven route layer.
- `src/chat_lms_agent/route_packs.py:60-69` — pack matching is AND over
  `required_tokens`. There is no OR/alias form, so a synonym set
  (`수업 뷰어 | 수업준비 | 보조패널 | …`) cannot be expressed in one pack.
- `routes/` contains classcard, gws-calendar, gws-schedule, gws-upload,
  kakao-channel. No wordbook pack, no lesson pack.
- On NO_MATCH the hook emits prompt deltas only
  (`commands.py:240-252`, `context.py:148-171`) — no hint that any routes or
  panels exist. The model has nothing to map intents against.
- `src/chat_lms_agent/side_panel.py:12-18` defines five views as contract
  concepts; the only runtime route is `lesson_wordbook`
  (`side_panel.py:128`). A correctly-detected lesson-prep intent has no
  executable target.
- `src/chat_lms_agent/side_panel_wordbook.py:101-107` expects
  `lesson_wordbook_server.py` + `lesson_wordbook_view.html` under
  `<profile>/<workspace>/scripts/`; missing assets → `WORDBOOK_RUNTIME_MISSING`
  (`:241-247`, reproduced on an empty profile). Nothing in the public repo
  materializes such assets: `scripts/bootstrap.ps1` writes only
  AGENTS/README/profile/memory/hydrate/CLI/hooks files; the python
  `bootstrap plan|apply|sync-runtime` subcommands are static stubs
  (`commands.py:302-316`); `doctor.py` has zero asset checks.
- `scripts/bootstrap.ps1` private hydrate template: wordbook-only routing
  rules plus a standing instruction to render tables/statistics/dashboards
  as **new HTML artifacts** under private reports. Combined with the missing
  route this *instructs* the hardcode-HTML failure mode.
- Toolchain: gates are `uv run ruff check` (ruff `select = ["ALL"]`),
  `uv run basedpyright` (`typeCheckingMode = "all"`), `uv run pytest -q`
  (198 tests green at plan time). Linux CI runs pytest with
  `--ignore=tests/test_bootstrap.py --ignore=tests/test_bootstrap_v2.py`.

## Design Decisions

- **D1 — one matching engine.** New function in `prompt_routes.py`
  (suggested: `resolve_prompt_route(prompt, repo_root, profile)`) that checks
  the built-in wordbook detector first, then route packs, and returns a
  uniform result (`kind: "builtin" | "pack"`, `route_id`, ready-to-emit route
  context dict, `student_hint` for builtin). Both the hook
  (`commands.py:_hook_emit_context`) and `prompt_check_payload` call it.
  Precedence (builtin first) is unchanged. For pack matches `prompt-check`
  emits the pack card as `route` with `status: "PASS"`; the wordbook-only
  `open_plan` attachment behavior stays builtin-only.
- **D2 — route-pack-v2 with `any_tokens`.** Loader accepts BOTH
  `route-pack-v1` (today's semantics, unchanged) and `route-pack-v2`, which
  adds optional `any_tokens: [str]`. Match rule: all `required_tokens`
  present (when non-empty) AND at least one `any_tokens` present (when
  non-empty); a v2 trigger pack must declare at least one of the two lists.
  Token comparison stays lowercase-substring, multi-word tokens allowed
  (`"수업 뷰어"`). `RoutePack` gains `any_tokens: tuple[str, ...]` (empty for
  v1).
- **D3 — NO_MATCH intent catalog.** A catalog builder produces compact cards
  for every loaded route (packs + the built-in wordbook route): `route_id`,
  `summary`, `first_command`. Injection rules: the hook adds
  `route_catalog` to its output only when no route matched AND the prompt
  contains a weak panel signal (module-level frozenset, e.g. `패널, 뷰어,
  화면, 보드, 현황, 보고, 리포트, 목록, 리스트, 열어, 보여, 띄워, 수업,
  단어, 학생, panel, viewer, dashboard, html, open`); `prompt-check` includes
  `route_catalog` on every NO_MATCH. The catalog carries an
  `instruction` field telling the model: map the request to one `route_id`,
  run its `first_command`, never author new HTML when a route exists, and
  record the mapping (D4). Catalog JSON is byte-capped (ceiling constant,
  1800 bytes, truncation marker pattern as `context.py:_budget_memory_section`).
- **D4 — route-use telemetry.** New command
  `agent-tools route record --route-id <id> --profile-root <root> --json`
  validates the id against loaded routes (+ builtin) and calls
  `usage_telemetry.record_surface_use(profile, f"route-catalog:{id}")`.
  Unknown id → exit 2, `error_code: "UNKNOWN_ROUTE_ID"`. This feeds future
  alias promotion (catalog hit → token in the pack).
- **D5 — lesson panel CLI surface mirrors wordbook.**
  `side-panel lesson open-plan --student <name> [--date YYYY-MM-DD]
  [--view lesson_prep] [--port N] --profile-root <root> --json`,
  `side-panel lesson ensure-server [--dry-run] [--port N] …`, and
  `side-panel lesson install-assets [--force] …`. Defaults:
  `DEFAULT_LESSON_PORT = 8766`; assets `lesson_panel_server.py` +
  `lesson_panel_view.html` under `<profile>/<workspace>/scripts/`; missing
  assets → `BLOCKED` + `error_code: "LESSON_RUNTIME_MISSING"` + the exact
  install command as `next_action`. Probe: `GET /api/health` must return
  200 JSON containing `"service": "lesson_panel"`; reuse the wordbook probe
  state machine (`running/not_running/wrong_service/unresponsive`). Factor
  shared probe/start/wait logic into a new `side_panel_runtime.py` consumed
  by both wordbook and lesson modules — wordbook public functions, error
  codes, and JSON shapes MUST NOT change (existing tests stay green
  unmodified).
- **D6 — fixed viewer + read-only API, templates in repo.** New
  `src/chat_lms_agent/side_panel_lesson.py` exposes
  `lesson_panel_payload(profile, student, lesson_date) -> dict` building a
  typed JSON payload from `academy_db` read helpers (discover the store
  shape from `academy_db.py` / `academy_db_parser.py` at implementation
  time). Missing/empty store → payload with empty sections and a warning
  entry; never raise. Repo ships templates under `assets/side-panel/`:
  `lesson_panel_server.py` (stdlib-only HTTP server, binds 127.0.0.1, takes
  `--port`, serves the view at `/`, `/api/health`, and
  `/api/lesson-panel?student=&date=` by importing
  `chat_lms_agent.side_panel_lesson` after inserting the placeholder
  `__REPO_SRC__` into `sys.path` and resolving profile root from placeholder
  `__PROFILE_ROOT__`) and `lesson_panel_view.html` (single file, no external
  resources, fetches `/api/lesson-panel` with its URL params and renders
  blocks from the documented catalog: `PanelHeader`, `WarningBanner`,
  `SummaryBlock`, `EntityList`, `TaskList`, `SourceCommandsFooter`; light +
  dark theme via the token axes in `side_panel.py:80-86`).
  `install-assets` copies templates with placeholder substitution, is
  idempotent, and refuses to overwrite existing files unless `--force`
  (files are user-owned after install; header comment in both templates must
  say so). This implements the documented architecture in
  `docs/side-panel-user-owned-html-css.md`: the agent never authors
  per-session HTML; payload contract and CLI live in the package.
- **D7 — asset guarantees + hydrate wording.** `scripts/bootstrap.ps1` User
  mode materializes the lesson assets when missing (copy + placeholder
  substitution in PowerShell, consistent with its existing template style;
  never overwrite without `-Force`). Doctor gains profile-mode rows:
  (a) per-panel runtime asset presence with repair action
  `side-panel lesson install-assets …`, (b) route-pack load warnings
  surfaced (malformed pack file names). The private hydrate template's
  wordbook-only rules generalize to: for any panel/viewer/lesson-prep/
  wordbook style request run `agent-tools prompt-check` first, follow the
  returned route or catalog `first_command`, and never create new HTML for
  such requests; the render-HTML-under-reports rule is rescoped to ad-hoc
  analyses *not covered by any route*.
- **D8 — lesson route pack.** `routes/lesson-assistant-panel.json`
  (`route-pack-v2`, bucket `trigger`, id `lesson_assistant_panel`):
  `any_tokens`: `"수업 뷰어", "수업뷰어", "수업준비", "수업 준비",
  "보조패널", "보조 패널", "수업 패널", "오늘 수업", "lesson prep",
  "lesson panel", "class viewer"`; `first_command` =
  `python -m chat_lms_agent side-panel lesson open-plan --student <student>
  --profile-root <root> --json`; `then_command` = ensure-server form;
  `fallback_command` = `python -m chat_lms_agent doctor --json`;
  `must_not` includes: no new HTML report, no new tool scaffold, no DB schema
  inspection before this route, no rg before this route.

### Non-goals (do NOT do these)

- No LLM/embedding calls inside the CLI; matching stays deterministic, the
  catalog exists precisely so the host model does the semantic mapping.
- No migration of the built-in wordbook route into a pack (recorded
  follow-up, intentionally out of scope — packs cannot extract
  `student_hint` yet).
- No Korean morphological analysis; substring tokens only.
- No visual redesign beyond the documented block catalog; the viewer is a
  functional user-owned starting template.
- No reading or writing of any real private profile; tests use tmp dirs via
  the hermetic conftest.

## Wave 1 — One matching engine + alias-capable packs

- [x] RED: tests for `route-pack-v2` parsing/validation: `any_tokens`
      accepted; v2 trigger pack with only `any_tokens` valid; v2 trigger pack
      with neither token list → validation warning; v1 packs parse unchanged
      with empty `any_tokens`.
- [x] RED: matching tests: any_tokens OR semantics, combined
      required+any semantics, multi-word Korean token substring match.
- [x] RED: parity tests: for a tmp v2 pack matching `수업준비 해줘`, BOTH the
      hook path (`resolve_prompt_route` as the hook uses it) and
      `prompt_check_payload` report the same `route_id`; builtin wordbook
      phrase parity too (`가상학생 단어 html 패널 열어줘` →
      `lesson_wordbook_status` on both paths).
- [x] GREEN: implement D2 in `route_packs.py` (accept both schema versions),
      D1 in `prompt_routes.py` + `commands.py` (hook delegates to the shared
      resolver; existing surface-use recording for matched routes preserved).
      `prompt_check_payload` NO_MATCH only when neither builtin nor pack
      matches; pack match → `status: "PASS"`, `decision` reflects reuse state
      as today.
- [x] Update `routes/README.md` with the v2 schema and matching rules.
- [x] GATE: `uv run ruff check` && `uv run basedpyright` && `uv run pytest -q`
      all green; commit (suggested: `feat(routes): unify prompt routing engine
      and add route-pack-v2 any_tokens`).

Wave 1 acceptance: with a tmp profile pack using `any_tokens: ["수업준비"]`,
`agent-tools prompt-check --prompt "수업준비 해줘" --profile-root <tmp> --json`
exits 0 with that pack's route card (this exact scenario currently fails).

## Wave 2 — Lesson CLI + lesson pack + NO_MATCH catalog + telemetry

- [x] RED: `side-panel lesson open-plan` on an assetless tmp profile →
      exit 4-or-5 (mirror wordbook's missing-asset code), `status: "BLOCKED"`,
      `error_code: "LESSON_RUNTIME_MISSING"`, `next_action` contains
      `side-panel lesson install-assets`.
- [x] RED: corpus test (new `tests/test_prompt_route_corpus.py`),
      parametrized, asserting BOTH engines return the same route per phrase:
      `학원 수업 뷰어 열어줘` → `lesson_assistant_panel`;
      `수업준비 해줘` → `lesson_assistant_panel`;
      `수업 보조패널 열어줘` → `lesson_assistant_panel`;
      `오늘 수업 패널 띄워줘` → `lesson_assistant_panel`;
      `lesson prep panel for tomorrow` → `lesson_assistant_panel`;
      `가상학생 단어 html 패널 열어줘` → `lesson_wordbook_status`;
      `과외 가상학생 학생 단어 현황 보고` → `lesson_wordbook_status`;
      `카카오 채널로 공지 보내줘` → `kakao_channel`;
      `고마워` → no route.
- [x] RED: catalog tests: hook output for `수업 화면 보여줘` (weak signal, no
      route — pick a phrase no pack matches) contains `route_catalog` with
      cards + `instruction`; hook output for `고마워` has NO catalog;
      `prompt-check` NO_MATCH always carries `route_catalog`; catalog blob
      respects its byte ceiling with truncation marker.
- [x] RED: `agent-tools route record --route-id lesson_assistant_panel` on a
      tmp profile exits 0 and the telemetry store gains
      `route-catalog:lesson_assistant_panel`; unknown id → exit 2
      `UNKNOWN_ROUTE_ID`.
- [x] GREEN: implement D3, D4, D5 (CLI surface + `LESSON_RUNTIME_MISSING`
      path only; runtime start logic may land as the shared
      `side_panel_runtime.py` refactor now or in Wave 3 — wordbook behavior
      byte-identical either way), D8 (`routes/lesson-assistant-panel.json`).
- [x] Extend `side_panel.py` hydration contract: `runtime_routes.lesson_panel`
      entry (triggers = the alias list, first/ensure/install commands) and
      extend `prompt_routing_policy_context()` with `lesson_requests`
      examples. Check `tests/test_context_budget.py` ceilings; if a section
      ceiling must grow, change it deliberately and update that test in the
      same commit.
- [x] GATE: gates green; commit (suggested: `feat(side-panel): lesson panel
      CLI surface, lesson route pack, NO_MATCH intent catalog`).

Wave 2 acceptance: the four Korean phrases above route at BOTH hook and
`prompt-check` level on a fresh tmp profile; `prompt-check` for an unmatched
panel-ish phrase returns the catalog instead of a bare NO_MATCH.

## Wave 3 — Lesson runtime: payload builder, templates, install-assets

- [ ] RED: `lesson_panel_payload` unit tests: empty/missing store → payload
      with declared empty sections + warning entry, never raises; populated
      fixture store → sections carry data; payload includes
      `source_commands` and passes
      `side_panel_validation.side_panel_payload_validate` written to a tmp
      file (conform to the existing validator's required shape — read
      `side_panel_validation.py` first and follow it).
- [ ] RED: `install-assets` tests: creates both files with placeholders
      substituted (no literal `__REPO_SRC__`/`__PROFILE_ROOT__` remain);
      second run without `--force` → no overwrite, `status` says skipped;
      `--force` overwrites.
- [ ] RED: server e2e test (python-only, Linux-safe): run installed
      `lesson_panel_server.py` via `subprocess` on a free ephemeral port
      (`--port`), poll `/api/health` until `service == "lesson_panel"`,
      GET `/api/lesson-panel?student=가상학생` → 200 typed JSON, then
      terminate the process. Mark with a generous timeout; no fixed port.
- [ ] RED: `ensure-server`/`open-plan` integration: with assets installed and
      a fake probe (monkeypatch as the wordbook runtime tests do),
      `open-plan` returns `browser_url` `http://127.0.0.1:8766/?student=…`.
- [ ] GREEN: implement D6 (payload builder, both templates, install-assets,
      ensure/open-plan runtime wiring through `side_panel_runtime.py`).
- [ ] GATE: gates green on Windows AND `uv run pytest -q
      --ignore=tests/test_bootstrap.py --ignore=tests/test_bootstrap_v2.py`
      green (Linux CI equivalence); commit (suggested:
      `feat(side-panel): lesson panel runtime — payload builder, fixed viewer
      and server templates, install-assets`).

Wave 3 acceptance: on a tmp profile —
`side-panel lesson install-assets` → `side-panel lesson ensure-server
--dry-run` reports startable → real `ensure-server` starts the server →
`open-plan` returns a `browser_url` whose `/api/lesson-panel` answers typed
JSON with empty-state sections.

## Wave 4 — Bootstrap materialization, doctor rows, hydrate wording, docs

- [ ] RED: doctor tests (profile mode): assetless profile → lesson asset row
      FAIL with repair action containing `install-assets`; installed profile
      → PASS; a malformed pack file in the profile routes dir → route-pack
      warning row listing the file name.
- [ ] RED: bootstrap test (in `tests/test_bootstrap_v2.py` style, Windows
      suite): User-mode run materializes lesson assets into the workspace
      scripts dir; re-run does not clobber a user-modified copy.
- [ ] RED: hydrate template content test: generated session-start script text
      contains the generalized routing rule (prompt-check-first for
      panel/viewer/lesson-prep/wordbook requests; no new HTML when a route
      exists) and the rescoped reports-HTML rule; wordbook-only rule text
      gone.
- [ ] GREEN: implement D7 (bootstrap.ps1 copy+substitute, doctor rows,
      hydrate template rewording).
- [ ] Update docs: `routes/README.md` (catalog behavior), `plans/STATUS.md`
      entry, and a short section in `docs/architecture.md` describing the
      `NL → route/catalog → fixed CLI → fixed viewer + read-only API`
      pipeline.
- [ ] GATE: gates green; commit (suggested: `feat(bootstrap,doctor): lesson
      panel asset guarantees and generalized routing guidance`).

Wave 4 acceptance (cold-start, end to end, tmp profile): bootstrap User mode
(or `install-assets`) yields a profile where `doctor` shows asset PASS rows;
all corpus phrases route on both engines; `수업준비 해줘` ends in an
executable `first_command` whose chain reaches a `browser_url`; the hydrate
script no longer instructs unconditional HTML-artifact rendering.

## Execution Protocol (binding for the implementing agent)

- TDD strictly: each checkbox's RED tests committed failing-then-green within
  the wave; never weaken an existing test to pass gates; wordbook behavior
  and its tests must remain untouched and green.
- Gates before EVERY commit: `uv run ruff check` && `uv run basedpyright` &&
  `uv run pytest -q`. Conventional commit style as in `git log`.
- Known toolchain traps (cost real debugging time before):
  - ruff ISC003 vs basedpyright `reportImplicitStringConcatenation` conflict
    — build long strings from intermediate variables inside one f-string.
  - On Windows `isatty()` is True for NUL: in subprocess tests pass
    `input=""` instead of `stdin=DEVNULL`.
  - `tests/conftest.py` (autouse) blanks secret-like env vars and redirects
    `CHAT_LMS_AGENT_PROFILE_ROOT` to a per-test tmp dir; rely on it, never
    point tests at a real profile.
- ruff runs with `select = ["ALL"]` and basedpyright in `all` mode — fully
  annotate new code; follow `JsonValue` typing patterns from existing
  modules; new modules need module docstrings only where ruff demands
  (D100/D101/D103/D104 are globally ignored).
- Public-safety: committed files must contain no real learner names (use
  `가상학생`), no machine-specific absolute paths, no secrets. Do not touch
  `evidence/`, `.omo/`, or any real profile directory.
- Any test that shells out to PowerShell belongs in the bootstrap test files
  (Linux CI ignores those); all other new tests must pass on Linux.
- Scope discipline: implement ONLY the wave named in your task. If a
  genuine blocker forces a design deviation, document it in the commit body
  and in `plans/STATUS.md` rather than silently changing contracts.
