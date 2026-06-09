# Side Panel Building Block Catalog

The agent may produce JSON payloads for these blocks. The user owns the visual HTML/CSS implementation.

| Block | Agent-owned contract | User-owned visual area |
| --- | --- | --- |
| `SidePanelShell` | size range, scroll behavior, theme metadata | shell styling |
| `PanelChrome` | title and status fields | chrome dots and live treatment |
| `PanelHeader` | entity, title, subtitle, privacy, time, schema | typography and spacing |
| `WarningBanner` | warning object schema | warning surface and icon |
| `SummaryBlock` | `summary` section schema | summary styling |
| `MetricGrid` | metric item schema and tone enum | grid and hero metric styling |
| `EntityList` | entity item schema and `entity_ref` | avatar, badge, list styling |
| `Timeline` | timeline item schema and state enum | dot and line styling |
| `TaskList` | task item schema and action intent | checkbox styling |
| `ActionGroup` | action intent, approval, dry-run policy | button styling |
| `SourceCommandsFooter` | provenance object schema | monospace footer styling |
| `ViewTabs` | view IDs, labels, icons | tab styling |
| `ThemeTokens` | token axes and allowed values | token implementation |
| `TweaksPanel` | optional design aid only | tweak UI implementation |
