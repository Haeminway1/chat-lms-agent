# Chat LMS Agent Agent Guide

This repository is intended to be safe for public source control.

## Boundaries

- Codex Desktop is the agent runtime.
- Do not add real learner records, private reports, saved secrets, or local machine paths.
- Keep runtime data in ignored local folders.
- Add tests before implementation.
- Ask for explicit confirmation before real external writes or destructive local changes.

## Development vs Real Use

- Open this repository only for OSS development.
- Open a private profile workspace for real lesson operations.
- The private profile workspace is created by `scripts/bootstrap.ps1 -Mode User -Profile <name>`.
- Product code, tests, public docs, skills, hooks, and reusable HTML blocks belong here.
- Real DB files, generated reports, logs, backups, local memory, and external account state belong outside this repo.
- If a Codex session is opened here, do not inspect or copy private profile data unless the user explicitly asks for migration, debugging, or setup.

## Verification

Run the focused contract tests before handing off changes:

```bash
uv run pytest tests/test_package_import.py tests/test_repo_privacy.py -q
```
