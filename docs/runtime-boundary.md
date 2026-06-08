# Development and Real-Use Workspace Boundary

Chat LMS Agent has two operating contexts.

## Development Workspace

Open the public source repository when building the product:

- package code
- tests
- public documentation
- Codex plugin metadata
- Codex skills
- hooks
- reusable HTML building blocks
- sample data

The development workspace must stay safe to publish. Do not place real learner records,
private reports, logs, backups, local memory, or saved secrets in the public repository.

## Real-Use Workspace

Open a private profile workspace when using the agent for real teaching operations:

- real class and tutoring records
- local DB files
- generated HTML reports
- backups
- automation logs
- private agent memory
- external account state

Create the private workspace with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -Mode User -Profile teacher-name
```

The generated private SessionStart hook safely syncs runtime wiring from the public
repo on every new Codex session. This updates generated private workspace files such
as `AGENTS.md`, profile metadata, hook config, and memory boundary notes. It does not
auto-import DB files, run schema migrations, change credentials, write external
systems, or perform destructive operations.

## Agent Rule

The short version belongs in each workspace `AGENTS.md`.
This document is the longer product note.

When the agent is working in the public repo, it should behave as an OSS developer and
avoid private data. When the agent is working in a private profile workspace, it should
behave as the teacher's local operations assistant and keep all runtime artifacts private.
