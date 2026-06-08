# Chat LMS Agent

Chat LMS Agent is a public-safe starter for a Codex Desktop local teacher LMS agent.
The teacher-facing interface is natural Korean conversation with Codex; the command
surface exists for deterministic setup, checks, and QA.

This repository intentionally starts with no real learner records, no private local
workspace details, and no saved secrets. Local runtime data belongs in ignored
workspace folders.

## Current Status

- Minimal Python package skeleton
- `chat-lms` command entry point
- Import, module execution, and privacy contract tests
- Ignore rules for local runtime artifacts

## Development

```bash
uv run pytest tests/test_package_import.py tests/test_repo_privacy.py -q
```

Future implementation should keep Codex Desktop as the only agent runtime and add
behavior through tests before production code.

## Real-Use Workspace

Use this repo for development. Use a private profile workspace for real teaching data.

Create or refresh a private workspace with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -Mode User -Profile teacher-name
```

That workspace lives under the user's local app data folder and contains real DB files,
reports, backups, logs, and private memory. It is intentionally separate from this
public repository so the repo can stay safe to publish.

The private workspace SessionStart hook auto-syncs safe runtime wiring from this repo,
so generated hook/AGENTS/profile changes can follow development without the teacher
remembering a manual command. Data imports, DB migrations, credentials, external writes,
and destructive changes still require explicit approval.
