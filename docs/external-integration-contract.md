# External Integration Contract

Every module that talks to the world outside the teacher's machine is an
**External Integration Module**. Use the service's own API/CLI when one
exists; build our own adapter when it does not. Each module declares four
axes in `src/chat_lms_agent/integration_modules.py`:

| Axis | Values | Meaning |
| --- | --- | --- |
| `capability_tier` | `official_api` · `official_cli` · `browser_automation` · `self_hosted` | How we reach the service |
| `setup_model` | `embedded_consent` · `per_user_account` · `per_user_channel` · `per_user_login` | How automatic the **external-account setup** for this integration can be — only `embedded_consent` (OAuth) reaches the pure one-consent Toss experience; the rest automate everything the law and vendor allow. (Per-integration consent design, not a general profile-onboarding flow — that is not implemented.) |
| `outward_writes` | `none` · `self_account` · `third_party` | Risk class of writes leaving the machine |
| `secret_path` | path under `~/.chat_lms_agent/` | Secrets live only in the user home — never in repo, hydration context, journals, or memory |

## Rules

1. **`third_party` writes (reaching another human) are approval-gated** —
   recipient-bound, single-use approvals via
   `evaluate_outward_send`/`consume_outward_send`, the pattern proven by
   `gws gmail send`. A mistyped recipient or a re-run can never reuse an
   approval.
2. **`self_account` writes** (the teacher's own accounts: calendar, sheets,
   own ClassCard classes) run directly and are trace-journaled.
3. Every module registers the discoverability triple: static registry
   entry with a `tool:<id>` memory obligation, a route pack banning
   browser automation for work data, and a doctor advisory row.
4. Browser automation of work data is allowed only where no API exists,
   classcard-style: one headed login, persistent profile, headless after,
   paced and never parallel.
