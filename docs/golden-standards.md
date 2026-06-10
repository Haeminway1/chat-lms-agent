# Golden Standards

Chat LMS Agent uses source-pinned references as structural standards, not as code to copy.

Canonical external reference decisions live in `docs/oss-reference-registry.md`.
This file is only a curated summary.

## lazycodex

- Adopted trait: command discovery through small reusable CLI tools.
- Local mapping: every reusable agent capability must be visible through `--help`, `list`, or `show`.
- Assumption: local golden-standard behavior was referenced by name; no source code is copied into this public repo.
- Must not copy: implementation internals or private runtime state.
- Evidence: CLI contract tests and capture transcripts.

## gajae-code

- Adopted trait: generated artifacts are drafts until tests, review, and evidence promote them.
- Local mapping: new side-panel views or blocks require proposal, schema, tests, and memory records before use.
- Assumption: treat gajae-code as a draft-to-reviewed-artifact workflow, not as reusable code.
- Must not copy: unreviewed generated UI or one-off scripts.
- Evidence: no-from-scratch tests and doctor checks.

## OMC

- Adopted trait: command catalog discipline and repeatable command surfaces.
- Local mapping: side-panel and DB operations must expose stable CLI namespaces before agents rely on them.
- Assumption: OMC is referenced as a command-management pattern; implementation details are not public repo inputs.
- Must not copy: private command registries, session logs, or machine-local config.
- Evidence: parser tests, CLI smoke checks, and context hydration inventory.

## OMX

- Adopted trait: execution evidence and machine-readable outputs before manual narrative.
- Local mapping: reusable agent work should produce JSON contracts, validation commands, and captured transcripts.
- Assumption: OMX is referenced as an execution/verification pattern; no internal code or data is copied.
- Must not copy: private transcripts, credentials, external account state, or runtime caches.
- Evidence: `scripts/qa/capture-command.ps1` transcripts and regression test outputs.

## oh-my-pi

- Adopted trait: pure-data decision contracts — approval tiers, canonical model identity, two-mode pseudonymization, consent-gated self-QA.
- Local mapping: PreToolUse decisions become a tier/policy/override table; the model catalog adopts classify/equivalence/selection semantics with concrete-id recording; privacy and self-QA ship as data-file contracts in profile state.
- Assumption: oh-my-pi is the upstream of gajae-code and is referenced for contract shapes only; its runtime, providers, and stream machinery are out of scope.
- Must not copy: yolo defaults, headless subagent autonomy, the multi-provider runtime, or any mechanism requiring a second agent loop.
- Evidence: decision-table truth-table tests, model-catalog resolver tests, pseudonymizer round-trip tests, and registry pinning in `docs/oss-reference-registry.md`.

## Hermes Agent

- Adopted trait: session continuity through durable state, hydration, and hook closeout.
- Local mapping: `context hydrate` includes tool, memory, and side-panel inventory; Stop blocks missing obligations.
- Assumption: Hermes Agent is referenced for continuity architecture, not for source-level reuse.
- Must not copy: messaging internals or external account state.
- Evidence: hook tests, context hydration tests, and closeout tests.
