# Shortcut Registry

`chat-lms shortcut` lets a teacher turn a repeated local action into a named,
deterministic CLI command. The public repo ships the engine only; shortcut
files live in the private profile under `.chat-lms-state/shortcuts/` and are
never committed here.

## Commands

- `shortcut list --profile-root <profile> --json` lists registered shortcuts as
  `name`, `description`, and `source`.
- `shortcut add --name <name> --run <command> [--description <text>]
  [--open-browser] --profile-root <profile> --json` validates and writes a
  `shortcut-v1` file in the private profile.
- `shortcut run --name <name> --profile-root <profile> --json` replays the
  registered command through the deterministic executor. If `open_browser` is
  true, the last non-empty stdout line is treated as the URL to open.
- `shortcut remove --name <name> --profile-root <profile> --json` deletes the
  private profile shortcut file.

## Trust Model

`shortcut run` replays only commands that the user registered with
`shortcut add`, similar to a shell alias. The registration step is the trust boundary:
once a command is stored in the user's private profile, running it
does not require another model approval gate.

The executor is deterministic. It does not call an LLM or resolve natural
language. Browser opening uses Python's stdlib `webbrowser` through an
injectable seam so tests can verify URL handling without launching a browser.
