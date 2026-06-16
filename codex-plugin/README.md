# Chat LMS Agent — Codex plugin

This directory is a **local Codex marketplace** that packages the
`chat_lms_agent` harness hooks as a Codex plugin, so Codex Desktop actually
executes them. Codex loads hooks only from registered plugins; dropping a
`hooks.json` inside a workspace does nothing (that was the original bug — the
harness wrote `codex-workspace/.codex/hooks.json`, which Codex never reads).

## Layout

```
codex-plugin/                              <- marketplace root (config.toml source)
  .agents/plugins/marketplace.json         <- declares the chat-lms-agent plugin
  chat-lms-agent/
    .codex-plugin/plugin.json              <- plugin manifest (hooks -> ./hooks/hooks.json)
    hooks/hooks.json                        <- maps each Codex event to the dispatcher
    scripts/chat-lms-hook.ps1               <- cwd-gated dispatcher
```

## How it stays scoped

The plugin is enabled globally, but `chat-lms-hook.ps1` only acts when the
Codex session's working directory is inside a Chat LMS teaching workspace
(a tree containing `.chat-lms-profile.json`). In every other project it emits
`{}` and exits — no routing, no context injection, no tool gating. The profile
root is derived as the parent of the workspace, so no machine-specific paths
live in this repo.

For non-`SessionStart` events the dispatcher forwards stdin to the workspace's
`scripts/chat-lms-cli.ps1` (`hook <event> --profile-root <root> --json`).
`SessionStart` runs the workspace's `scripts/session-start-hydrate.ps1`.

## Register (one time, per machine)

Add to `~/.codex/config.toml`:

```toml
[marketplaces.chatlms]
source_type = "local"
source = '<repo-root>\codex-plugin'

[plugins."chat-lms-agent@chatlms"]
enabled = true
```

Then start a new Codex session. On first run Codex asks you to trust the
plugin's hooks (the same trust prompt omo went through); approve it. From then
on, lesson/wordbook prompts hit the deterministic CLI fast-path.
