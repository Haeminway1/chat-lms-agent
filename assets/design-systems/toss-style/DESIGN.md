# Toss-Style Side Panel Design System

## Identity
Summary: Toss-style default design system for calm, mobile-first side panels.

Use this design system when a teacher needs a narrow lesson or learner panel that feels clear before it feels decorative. The interface should make the next action obvious, keep the teacher's attention on learner state, and avoid visual tricks that compete with instructional decisions.

## Color
Use `#3182F6` as the single accent color for primary actions, selected states, and important interactive affordances. Keep the rest of the palette neutral, with white or near-white surfaces in light mode and deep neutral surfaces in dark mode. Use semantic status colors only when they carry real state such as warning, success, or danger.

## Typography
Use `Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif` as the font stack. Keep panel text readable at small widths: concise headings, body text in the 13px to 18px token range, and enough line height for Korean and English mixed text.

## Spacing
Favor generous whitespace over dense packing. The panel should read as one vertical column with clear blocks, predictable gaps, and enough padding for touch use. Compact layouts may reduce vertical gaps, but they must not collapse hierarchy or make controls hard to tap.

## Components
Build from side-panel blocks: shell, header, warning banner, summary, entity list, task list, action group, and source-command footer. Use cards only for repeated items or bounded groups. Prefer simple rows, clear labels, and direct actions over decorative containers.

## Motion
Use restrained motion only for state changes that benefit from continuity, such as opening a detail row or confirming a saved preference. Keep durations short, avoid bounce effects, and respect reduced-motion preferences.

## Voice
친절한 존댓말로 짧고 분명하게 안내합니다. 교사가 바로 판단할 수 있도록 상태, 이유, 다음 행동을 먼저 말하고, 과장된 표현이나 마케팅 문구는 사용하지 않습니다.

## Accessibility
Preserve contrast in both themes, keep touch targets at least 44px, do not rely on color alone for status, and keep focus states visible. Text must wrap within the 372px panel shell without horizontal scrolling.

## Anti-patterns
Do not use horizontal carousels. Do not use dense tables in panel mode. Do not use decorative gradients, purple-blue gradient backgrounds, nested UI cards, hidden remote assets, tiny tap targets, or hardcoded learner-looking data inside the HTML.
