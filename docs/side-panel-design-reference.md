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
- Required views: `class_overview`, `learner_detail`, `attendance_summary`, `session_record`, `homework_status`.

## Recommended Traits

- A/B/C variants for list, metric hero, and operation timeline layouts.
- Default accent `#3182F6`.
- Pretendard-style Korean UI typography.
- Density, roundness, accent, theme, and font size token axes.

## Out Of Scope

- Raw prototype HTML, CSS, JSX, CDN host, screenshots, or Babel dev wiring.
- Agent-authored visual redesign.
- Real learner or class data.
