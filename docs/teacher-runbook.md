# Teacher Runbook — isolated real-use setup + daily 기입

Plain steps to go from a fresh download to recording a class day, in a Codex
environment isolated from any other tooling you run. Public-safe: replace
`<...>` placeholders with your own values; nothing machine-specific is stored
in this repo.

## One-time setup

1. **Get the code + toolchain.** Clone this repo, then in the repo root:
   ```bash
   uv sync --dev
   ```
2. **Provision your private workspace + isolated Codex home.** From the repo root:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -Mode User -Profile <your-name>
   ```
   This creates, under your local app-data profile root:
   - `codex-workspace/` — the real-use workspace (AGENTS.md, hooks, CLI wrapper, profile marker);
   - `data/chat_lms.db` — your private learner database (never enters this repo);
   - **`codex-home/config.toml`** — a clean Codex home that enables **only** the
     chat-lms plugin (no third-party plugins, no agent-orchestration manifesto
     merge, no telemetry);
   - **`codex-home/launch-teacher-codex.cmd`** — a launcher that points Codex
     Desktop at that clean home.

   The command also prints the two paths (`TEACHER_CODEX_HOME`,
   `TEACHER_CODEX_LAUNCHER`).

3. **First launch (two security clicks Codex requires — these cannot be
   automated, and shouldn't be):**
   - **Fully quit** any running Codex Desktop (close all windows and exit from
     the tray) — it is single-instance, so a running copy would ignore the new
     home.
   - Double-click `launch-teacher-codex.cmd` (pin it as "Codex (Teacher)").
   - In that session, run `codex login` once (auth is per-home).
   - Open the `codex-workspace` folder; approve the one-time **chat-lms
     hook-trust** prompt.

4. **Verify the isolation took.** In a teacher session, confirm the standing
   context shows the "Chat LMS Agent Runtime Context" + the Korean-answer rule,
   and contains **none** of: a "never stop / spawn agents / ultrawork"
   manifesto, third-party code MCP tools, or extra agent roles. If it does, you
   launched the wrong home — quit and relaunch via the launcher.

5. **Register the 기입 write-action once (the trust boundary).** Recording a
   class is gated on a teacher-approved registration:
   ```powershell
   # 1) request registration (prints an approval id)
   <cli> write-action register --id record-class --profile-root <profile-root> --json
   # 2) approve it in a REAL terminal (you must type the approval id by hand)
   <cli> approval approve --id <approval-id> --actor <your-name>
   ```
   Do the same once for `record-test-scores` if you record test scores. After
   this, daily recording runs unattended. (`<cli>` = the workspace
   `scripts/chat-lms-cli.ps1`.)

## Daily use — recording a class

Just talk to the agent in Korean, e.g.:

> EBSS 전원 출석, 숙제 100, 진도 unit 1 weekly test, 점수 원우 13/15 하린 12/15

The agent then runs a fixed, deterministic flow (no hand-written SQL):
1. **roster** — `write-action roster --class-code <code>` resolves the class's
   enrolled students to their ids.
2. **fill** — it fills the `record-class` payload (and `record-test-scores` if
   there were scores) with those ids + your numbers.
3. **apply** — `write-action apply` runs one backed-up atomic transaction:
   inserts the session, UPDATEs each student's auto-created attendance/homework
   stub (never blind-inserts — so no NULL-attendance rows), and records scores.

A class day records in seconds, with an ID/count-only audit row and an
automatic pre-write DB backup.

## Repairing older hand-entered rows

If earlier days were entered by hand and left a student's attendance NULL,
re-run `record-class` for that class+date with the correct attendance — the
`update_stub` step fills the existing rows in place. Verify with the academy
daily viewer or a read query.

## Notes & guardrails

- **ClassCard upload is unchanged** and works in the isolated home (it uses its
  own bundled browser, not any third-party plugin).
- **Never set `CODEX_HOME` at User/Machine scope on your dev account** — that
  would strip your dev tooling from dev sessions. Keep the override inside the
  teacher launcher only.
- **Graduate option (footgun-free):** run a dedicated Windows account for
  teaching with `CODEX_HOME` set at that account's User scope — then the
  Start-menu tile / protocol launches inherit the clean home automatically, no
  launcher discipline needed.
- Both homes depend on this repo's path existing; if you move the repo, re-run
  bootstrap so the generated wiring points at the new location.
