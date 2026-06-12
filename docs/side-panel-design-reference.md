# Side Panel Design Reference

The user-provided side-panel HTML prototype is the design reference for future 보조 패널 work.
It is not a production artifact to copy into the public repo.

## Sufficiency Verdict

The prototype is sufficient as a design origin and building-block reference.
It is not sufficient by itself as an enforcement harness.

## Required Traits

- Narrow and tall shell, approximately `372px x 760px`.
- Panel chrome with `보조 패널 · side-panel` and live/status affordance.
- Header metadata: `entity_ref`, `title`, `subtitle`, `privacy_level`, generated time, and schema version.
- Warning-first flow immediately after the header.
- Registered sections only: `summary`, `metric_grid`, `entity_list`, `timeline`, `task_list`, `action_group`.
- Source command footer for CLI provenance.
- Light and dark token parity.
- Required views: `class_overview`, `learner_detail`, `attendance_summary`, `session_record`, `homework_status`, `lesson_prep`.
- Lesson prep runtime uses the registered `lesson_prep` view with `summary`, `entity_list`, and `task_list` sections, plus warnings and source command provenance rendered by the fixed user-owned template.

## Display Spec v1

The machine-readable display contract lives at `assets/side-panel/display-spec-v1.json`.
It defines the mandatory `panel` mode as a 372px by 760px base viewport with
a 360px to 480px width band, single-column layout, forbidden horizontal
scroll, allowed vertical scroll, 44px minimum touch targets, and the
`fontSize` token axis constrained to 13 through 18.

The same contract defines the recommended `fullscreen` mode as any viewport
at least 1024px by 768px, with multi-column layout allowed while
document-level horizontal scroll remains forbidden.

| Mode | Viewport Contract | Layout | Horizontal Scroll | Required In Artifact |
| --- | --- | --- | --- | --- |
| `panel` | Base `372px x 760px`; width band `360px`-`480px` | Single column | Forbidden on document and shell | Yes |
| `fullscreen` | Minimum `1024px x 768px`; verified at `1440px x 900px` | Multi-column allowed | Forbidden at document level | Recommended; declare with `panel fullscreen` |

## Recommended Traits

- A/B/C variants for list, metric hero, and operation timeline layouts.
- Default accent `#3182F6`.
- Pretendard-style Korean UI typography.
- Density, roundness, accent, theme, and font size token axes.

## Out Of Scope

- Raw prototype HTML, CSS, JSX, CDN host, screenshots, or Babel dev wiring.
- Agent-authored visual redesign.
- Real learner or class data.
