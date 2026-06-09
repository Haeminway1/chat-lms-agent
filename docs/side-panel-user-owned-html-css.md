# User-Owned Side Panel HTML/CSS

The user owns side-panel visual building blocks. The agent owns the payload contract, validator, registry, and CLI integration.

## Agent Must Not

- Create standalone side-panel HTML from scratch.
- Add unregistered section types.
- Write CSS before a payload schema and validator exist.
- Create action buttons without `intent`, `requires_approval`, and `dry_run_default`.
- Produce production payloads without `source_commands`.

## Agent May

- Build JSON payloads for registered blocks.
- Validate payloads with `side-panel payload validate`.
- Draft a new view proposal without generating HTML/CSS.
- Record memory and decision obligations for new side-panel work.

## Handoff Contract

User-authored HTML/CSS should consume the JSON shape from `side-panel spec --json`.
Any new visual block must first become a documented block proposal.
