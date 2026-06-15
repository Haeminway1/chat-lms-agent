# Academy Viewer One-Command Open + User Shortcut Registry Plan

Status: PLAN ONLY — not approved for implementation yet. Two tiers; each is
independently shippable. Tier 1 is a near-zero-build fix to the immediate
pain; Tier 2 is the general capability the teacher asked for.

Author: 2026-06-15 diagnosis session (live-reproduced evidence below).

## Purpose

Opening the teacher's EXISTING academy daily viewer took 3+ minutes in a live
session. A fast, daily, repeated action was forced through the slow
`natural-language → route → agent multi-step ceremony` path. It must instead be
a **single CLI command that opens in seconds**, and the harness should let the
teacher turn ANY repeated action into such a command (the harness does not
bundle the viewer; it shapes the teacher's own repeated action into a reusable
CLI surface).

## Verified Current State (live, 2026-06-15)

- `agent-tools prompt-check --prompt "학원 수업 뷰어 열어줘"` **without**
  `--profile-root` → `NO_MATCH`; **with** `--profile-root` → `PASS
  academy_daily_viewer`. Reproduced. The workspace wrapper
  `<workspace>/scripts/chat-lms-cli.ps1` does NOT inject `--profile-root`, so a
  manually-run prompt-check cannot see the profile route the teacher installed
  → agent concludes "no route" → improvises (the 3-minute hunt). **(R1)**
- The `UserPromptSubmit` hook IS wired with `--profile-root` (bootstrap), so the
  route is already injected into session context. The agent's manual
  prompt-check re-run is therefore both redundant and broken.
- `<workspace>/scripts/open_academy_daily_viewer.ps1` regenerates today's
  viewer (`academy_report.py`) + serves it on 127.0.0.1:8765-8774 + prints the
  URL, but does NOT open a browser (its only `Start-Process` launches the
  http.server). The agent had to do git-bash path conversion + Browser-plugin
  connection/doc-reading to actually display it. **(R2)**
- Profile route `academy_daily_viewer` (at
  `<profile>/.chat-lms-state/routes/academy-daily-viewer.json`) `first_command`
  currently runs the opener, which returns a URL only.
- Root cause: a known, repeated action is routed through NL intent resolution
  plus a multi-step open ceremony, instead of one deterministic command.

## Tier 1 — academy viewer = one command (private workspace + small bootstrap edit; immediate)

Goal: running ONE command opens the viewer in seconds, with no scaffolding and
no browser ceremony.

- **T1-D1 (R2 fix) — opener opens the browser itself.** In
  `open_academy_daily_viewer.ps1`, after the URL is confirmed serving (the
  existing 200 health check), open the default browser
  (`Start-Process $url`). Idempotent; if a browser is already on that URL it
  just focuses/opens a tab. Net: "run the opener" == "viewer is on screen".
  (Private-workspace file — confirm before editing.)
- **T1-D2 — discoverable single command.** Document the one command in the
  workspace `AGENTS.md`/`README` so the teacher can type it directly without
  any agent:
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/open_academy_daily_viewer.ps1`
- **T1-D3 (R1 fix) — stop the redundant manual prompt-check.** Update the
  bootstrap private-hydrate guidance (`scripts/bootstrap.ps1`, public repo) so
  the agent is told: the matched route is ALREADY injected by the hook —
  run its `first_command` directly; do NOT manually re-run `agent-tools
  prompt-check` (and if you ever do, it requires `--profile-root`). Removes the
  arg-format fumble and the missing-profile-route miss.

Checklist:
- [ ] T1-D1: opener appends a browser-open after the health check; manual smoke
      shows a tab opening.
- [ ] T1-D2: workspace AGENTS.md/README documents the single command.
- [ ] T1-D3: bootstrap hydrate wording updated (+ its content test in
      `tests/test_bootstrap_v2.py` adjusted); gates green; commit + push.
- [ ] Live smoke in a fresh workspace session: "학원 수업 뷰어 열어줘" →
      viewer visible in well under a minute, one action.

Acceptance: from a cold session, the viewer opens in ~seconds with one command
and zero scaffolding/ceremony. R1 and R2 both gone.

Scope note: Tier 1 edits one private-workspace script (opener) + public
`bootstrap.ps1` hydrate wording. No new repo subsystem.

## Tier 2 — `chat-lms shortcut` registry (public repo; the general capability)

Let a user register a repeated action as a named, deterministic CLI command.
Mirrors the repo's data-driven pattern (route packs): repo ships none; the
private profile holds the user's shortcuts. A shortcut is a pure store-and-
replay of a command the user authored — no LLM in the execution path.

- **T2-D1 — `shortcut-v1` data files.**
  `<profile>/.chat-lms-state/shortcuts/<name>.json`:
  ```json
  {
    "schema_version": "shortcut-v1",
    "name": "academy-viewer",
    "description": "오늘 학원 수업 리스트 뷰어 생성+열기",
    "run": "powershell -NoProfile -ExecutionPolicy Bypass -File <path>/open_academy_daily_viewer.ps1",
    "open_browser": true
  }
  ```
  Loader mirrors `route_packs.load_*` (profile dir scan, one malformed file →
  warning, never aborts). Shortcuts are profile-only; never shipped in the repo.
- **T2-D2 — `chat-lms shortcut` CLI (pure executor, no LLM):**
  - `shortcut list [--profile-root] --json` → name/description/source per
    registered shortcut.
  - `shortcut add --name <n> --run <cmd> [--description <d>] [--open-browser]
    [--profile-root] --json` → validate (non-empty name + run) and write the
    file (overwrite by name).
  - `shortcut run --name <n> [--profile-root] --json` → execute the registered
    `run` via subprocess; if `open_browser`, take the last stdout line as a URL
    and open it via Python stdlib `webbrowser.open`; return
    `{status, name, exit_code, url?, stdout_tail}`. Deterministic; no model.
  - `shortcut remove --name <n> [--profile-root] --json` → delete the file.
- **T2-D3 — trust model.** `shortcut run` replays ONLY what the user registered
  via `shortcut add` (like a shell alias). Shortcut files live solely in the
  private profile; the registration step is the trust boundary, so `run` needs
  no extra approval gate. Document this explicitly.
- **T2-D4 — bind NL → one command.** Register the academy viewer as a shortcut
  (`run` = opener, `open_browser` = true) and change the
  `academy_daily_viewer` route `first_command` to
  `chat-lms shortcut run --name academy-viewer`. Both the teacher (direct) and
  the agent (via route) then do exactly one deterministic thing.
- **T2-D5 — host independence.** Browser opening uses Python stdlib
  `webbrowser` (cross-platform) behind an injectable seam; repo core stays
  host-token-free and path-free (paths live only in profile shortcut files).

Checklist (TDD; gates before every commit):
- [ ] RED: loader tests (profile shortcuts load; malformed file → warning,
      others still load); `shortcut-v1` validation (name + run required).
- [ ] RED: CLI contract tests — `add` writes a file; `list` shows it; `run`
      executes a harmless fake command (e.g. `echo`) and returns exit_code +
      stdout_tail; `open_browser` path opens via a MONKEYPATCHED seam (no real
      browser, no network in tests); `remove` deletes.
- [ ] GREEN: `shortcuts.py` (loader + `shortcut-v1` validation), CLI handlers +
      parser, `webbrowser` open seam (injectable).
- [ ] Docs: `docs/shortcuts.md` + one line in `docs/architecture.md`.
- [ ] GATE: `uv run ruff check` && `uv run basedpyright` && `uv run pytest -q`,
      plus the linux-ignore run; commit + push.

Acceptance: `chat-lms shortcut add --name academy-viewer --run "<opener>"
--open-browser` then `chat-lms shortcut run --name academy-viewer` opens the
viewer in seconds; "학원뷰어 열어줘" resolves to that single command.

## Non-goals

- The harness does NOT bundle the academy viewer; shortcuts only store+replay
  user-authored commands.
- No LLM in `shortcut run` — it is a deterministic executor.
- No remote/destructive command policy beyond "the user registered it";
  shortcuts are private-profile only and never enter the public repo.
- No real learner data, real names, secrets, or machine paths in the public
  repo (paths live only in profile shortcut files; tests use `가상` + fakes).

## Execution Protocol (when approved)

Same as `plans/prompt-intent-routing-and-lesson-panel-plan.md` Execution
Protocol: TDD red→green, gates before every commit, hermetic conftest, the
ruff-ISC003/NUL-isatty traps, public-safety `가상`-only. Additionally: NO real
browser launch and NO real subprocess side effects in tests — inject the
`webbrowser.open` and command-runner seams and assert on captured calls.

## Recommended order

Tier 1 first (kills today's 3-minute pain immediately, tiny surface), then
Tier 2 (generalizes it; folds the academy viewer into the shortcut registry and
points the NL route at the one-command shortcut).
