# Harness V3 Red Test Execution

## Development Approach

- Add focused V3 contract tests first, then implement the smallest cohesive modules needed to satisfy them.
- Keep new ledger behavior in dedicated modules rather than growing parser, doctor, or state responsibilities.
- Preserve V2 command compatibility while adding V3 command surfaces.
- Store every runtime ledger under `<profile-root>/.chat-lms-state/` and expose only redacted placeholders in CLI JSON.

## Test Plan

- Run targeted V3 tests for trace/audit, approval policy, academy DB imports/params/doctor, and V3 context/doctor/closeout inventory.
- Run focused regression tests for package import and public repo privacy.
- Run existing academy DB/context/doctor/closeout tests to protect V2 compatibility.

## Success Criteria

- Missing approval for `academy-db import apply` returns JSON status `NEEDS_APPROVAL` and process exit code `3`.
- Agent self-approval is rejected.
- Trace, audit, and approval records include schema versions and redact private paths/secrets/learner-like raw text.
- Context hydration, doctor, and closeout expose V3 operating inventory without leaking profile paths.
- Public repo privacy tests remain green.

## Failure Criteria

- Runtime trace/audit/approval/import files appear in the public repository.
- Import apply can run without a valid non-self approval.
- Query params are accepted without schema validation.
- Context, doctor, or closeout omit V3 inventory expected by the plan.
- Any existing focused V2 contract regresses.
