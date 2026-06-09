# Agent Tool Registry

This public repository stores reusable agent tool contracts, not runtime data.

The registry gives each new Codex session a stable way to discover approved
tooling before inventing work from scratch. The current public foundation tools
are:

- `side-panel`: Codex Desktop auxiliary panel building blocks and payload
  validation.
- `academy-db`: planned academy database setup and operations workflow contracts.

Every reusable tool must define:

- `id`: stable tool id.
- `summary`: what the tool is for.
- `command_contract`: the CLI command or commands the agent should run.
- `memory_obligation`: what durable memory must be updated when the tool changes.

Runtime files, real learner records, generated reports, logs, backups, external
account state, and profile memory stay outside this repo in the user profile
runtime boundary. Public code may describe the shape of a tool, but it must not
store private operational data.

Use this command to inspect the registry:

```bash
python -m chat_lms_agent agent-tools list --json
```

Use this command before adding a new reusable tool:

```bash
python -m chat_lms_agent agent-tools validate --from <proposal.json> --json
```
