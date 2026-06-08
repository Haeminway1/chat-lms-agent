# Chat LMS Agent DB + 보조 패널 Harness Plan

## TL;DR
> **목표**: Chat LMS Agent를 학원/수업 운영에 맞는 `CLI-first DB 운영 하네스 + 자동 memory/context 하네스 + 보조 패널(side panel) 데이터 계약` 구조로 확장한다.
>
> **핵심 결정**:
> - 오른쪽 UI 표면의 공식 명칭은 앞으로 **보조 패널(side panel)** 이다.
> - DB 구축/확장/수정/조회/운영은 에이전트가 매번 직접 새로 만들지 않고, 표준 CLI와 registry를 통해 수행한다.
> - 새 도구, DB schema, migration, named query, hook, 보조 패널 view가 생기면 structured memory/decision record가 반드시 남아야 한다.
> - 새 세션은 `context hydrate`/SessionStart를 통해 사용 가능한 DB 도구, query, schema snapshot, 보조 패널 view inventory를 자동으로 안다.
> - 보조 패널의 CSS/HTML building blocks와 visual guideline은 사용자가 직접 만든다. 이 계획은 구현하지 않고 방향, contract, CLI integration, 검증 방식만 정의한다.

## 현재 Baseline
- 현재 command tree는 `doctor`, `context`, `onboarding`, `profile`, `tool`, `memory`, `session`, `hook`, `bootstrap`를 노출한다.
- 현재 tool/memory는 v1 수준의 registry와 hydration을 제공하지만, DB 운영과 학원 도메인 query 표준은 아직 없다.
- 현재 public/private 경계는 이미 문서화되어 있다:
  - public repo: 제품 코드, 테스트, 공개 문서, hook, sample fixture, 재사용 가능한 block/spec
  - private profile workspace: 실제 DB, 학생/수업 데이터, 보고서, 로그, 백업, private memory
- 기존 계획은 self-maintaining harness의 기본기를 다루며, 이번 계획은 그 다음 단계인 **DB 운영 계층**과 **보조 패널 데이터 계층**을 추가한다.

## Golden Standard 참조 방식
이 계획은 `lazycodex`, `가제코드`, `Hermes Agent`를 코드 복사 대상이 아니라 구조적 기준으로 사용한다. 구체 구현체/문서가 repo에 pin되어 있지 않으므로, 첫 작업은 canonical source를 기록하고 trait checklist로 고정하는 것이다.

### lazycodex에서 채택할 구조
- 도구를 매번 재발명하지 않고, 필요한 순간 빠르게 발견하고 실행하는 CLI catalog.
- 에이전트가 자연어 판단을 맡고, 반복 실행은 command/tool이 맡는 구조.
- 명령어 help/list/show가 곧 agent memory의 일부가 되는 discoverability.
- 작고 빠른 명령을 조합하는 방식. 하나의 거대 script가 모든 운영을 삼키지 않는다.

### 가제코드에서 채택할 구조
- scaffold와 generated artifact를 무조건 즉시 신뢰하지 않고, review/test/evidence를 통해 승격하는 방식.
- 반복 패턴은 template/spec으로 고정하고, 변형은 registry에 기록한다.
- 생성물의 provenance, decision, acceptance criteria를 남겨 다음 세션이 같은 판단을 반복하지 않게 한다.

### Hermes Agent에서 채택할 구조
- 세션 간 연속성을 message/state/context hydration으로 유지하는 방식.
- tool registry, memory ledger, decision record를 분리해서 관리하는 방식.
- hook/event 기반으로 SessionStart, PostToolUse, PostCompact, Stop 시점에 상태를 갱신하거나 검증하는 방식.

### Golden Standard 검증 규칙
- 모든 새 architecture 작업은 `docs/golden-standards.md`의 checklist를 통과해야 한다.
- checklist에는 `source`, `adopted_trait`, `local_mapping`, `must_not_copy`, `test_or_QA_evidence` 필드가 있어야 한다.
- source가 pin되지 않은 golden standard trait는 구현 의존성으로 사용하지 않는다. 우선 "assumption"으로 기록하고 구현 gate에서 차단한다.

## 용어 규칙
- 사용자-facing 이름: `보조 패널`
- 병기: `보조 패널(side panel)`
- CLI namespace: `side-panel`
- JSON/memory key prefix: `side_panel`
- 문서 파일명: `side-panel`
- 금지: `right panel`, `우측패널`, `assistant panel`, `html panel`을 새 공식 명칭으로 쓰지 않는다. 기존 문서에 남아 있는 표현은 migration task에서 치환한다.

## Scope
### 포함
- DB CLI namespace 설계와 단계별 구현 계획
- 학원/수업 관리 domain model의 public-safe schema/template 계획
- named query registry와 query CLI 계획
- DB migration/backup/restore/doctor/rollback gate 계획
- structured memory/decision record 확장 계획
- SessionStart/context hydration 확장 계획
- 보조 패널 데이터 contract, payload validation, refresh lifecycle 계획
- 보조 패널 CSS/HTML guideline을 사용자가 작성할 수 있게 하는 Markdown skeleton 계획

### 제외
- 실제 CSS/HTML building block 구현
- 실제 보조 패널 visual design 작성
- 실제 학생/학부모/강사/수업 데이터 작성
- 실제 외부 LMS/결제/메신저 write 연동
- real profile workspace의 private DB를 public repo에서 읽거나 복사하는 작업

## Target Architecture
```text
Natural Korean request
  -> Agent interpretation
  -> CLI-first command selection
  -> Private profile DB / registry / memory
  -> JSON result
  -> Optional 보조 패널 payload
  -> SessionStart hydration remembers the tool/query/schema inventory
```

## 사용자 제공 보조 패널 HTML 분석 반영
사용자가 제공한 `html 사이드패널.zip`은 그대로 복사할 최종 구현물이 아니라, 향후 보조 패널의 **디자인 기준점**이다. 구현 단계에서는 시각적 방향과 정보 구조를 약 90% 적극 활용하되, 더미 데이터와 임시 prototype wiring은 CLI/runtime payload로 교체한다.

### Sufficiency Verdict
판단: 제공된 zip은 **디자인 원형과 기초 빌딩 블록으로는 충분하다.** 하지만 **에이전트가 멋대로 HTML을 만들지 못하게 하는 강제 하네스**로는 아직 충분하지 않다.

충분한 것:
- 보조 패널의 기본 shell, chrome, header, scroll body, footer 구조.
- 학원 운영에 맞는 v1 view 후보.
- 반복 가능한 section building block.
- light/dark theme, density, roundness, accent, font-size token 축.
- A/B/C variant를 통한 view별 표현 전략.
- `source_commands`를 통한 CLI provenance 방향.

부족한 것:
- 공식 JSON schema와 strict validator.
- section/view registry와 unknown section 차단 규칙.
- action button의 `intent`, approval, dry-run 정책.
- `source_commands`의 실행 provenance object shape.
- memory/hook/doctor와 연결된 side-panel change obligation.
- raw HTML/CSS를 agent가 새로 만들지 못하게 하는 no-from-scratch gate.

따라서 이 zip은 **보조 패널 표준의 원재료**로 승격한다. 실행 계획은 zip을 다음 세 가지 산출물로 바꾸는 것을 목표로 한다.
- `docs/side-panel-design-reference.md`: 디자인 기준과 빌딩 블록 설명.
- `side-panel payload schema`: 어떤 데이터만 렌더 가능한지 고정하는 contract.
- `side-panel validator/doctor/hook`: agent가 임의 HTML/section/view를 만들지 못하게 하는 강제 장치.

### 포함 파일에서 확인한 구조
- `보조 패널.html`: React/Babel prototype host. Pretendard, React 18, `styles.css`, `data.jsx`, `sections.jsx`, `panel.jsx`, `app.jsx`, `tweaks-panel.jsx`를 조립한다.
- `app.jsx`: view tabs, light/dark theme, design tweak system, 3개 variant 비교 stage를 제공한다.
- `data.jsx`: `class_overview`, `learner_detail`, `attendance_summary`, `session_record`, `homework_status` view와 payload 예시를 제공한다.
- `panel.jsx`: panel chrome, header metadata, warning area, section rendering, source command footer를 제공한다.
- `sections.jsx`: `summary`, `metric_grid`, `entity_list`, `timeline`, `task_list`, `action_group`, warning renderer를 제공한다.
- `styles.css`: Toss-like light/dark tokens, fixed narrow/tall panel shell, density/round/accent/font-size tokens, A/B/C variant styling을 제공한다.
- `tweaks-panel.jsx`: accent, density, round, font size, dark mode를 조절하는 edit/tweak control protocol을 제공한다.
- `screenshots/*.png`: light/dark, tall, expanded, variant 비교 상태의 visual QA reference를 제공한다.

### 90% 활용할 디자인 DNA
- 기본 패널 비율은 **세로로 긴 372px x 760px 전후의 narrow panel**을 기준으로 한다.
- panel chrome에는 `보조 패널 · side-panel`, live 상태, scrollable body를 유지한다.
- header는 `entity_ref`, `title`, `subtitle`, `privacy_level`, `generated_at`, `schema_version`을 항상 보여준다.
- warning은 header 직후 상단에 배치해서 운영 리스크를 먼저 보이게 한다.
- section 순서는 `summary -> metric_grid -> entity_list/timeline -> task_list -> action_group -> source_commands`를 기본으로 한다.
- `source_commands` footer는 유지한다. 보조 패널은 예쁜 화면이 아니라 **어떤 CLI 결과에서 생성됐는지 추적 가능한 운영 표면**이어야 한다.
- light/dark theme은 같은 정보 위계를 유지하는 token parity로 설계한다.
- 디자인 token은 `accent`, `fontSize`, `density`, `round`, `theme`를 최소 핵심 축으로 유지한다.
- A/B/C variant는 보조 패널 view template 전략으로 보존한다:
  - A `정석 리스트형`: learner detail, homework status처럼 항목 확인 중심 view에 적합.
  - B `지표 강조형`: class overview, attendance summary처럼 핵심 수치가 먼저 보여야 하는 view에 적합.
  - C `오퍼레이션형`: session record, daily operations처럼 timeline과 action이 중요한 view에 적합.
- task/action은 실제 write가 아니라 **action intent payload**로 먼저 표현한다. 실행은 별도 CLI approval/dry-run gate를 통과해야 한다.

### 그대로 쓰지 않을 것
- 더미 learner/class 이름과 prototype sample data는 그대로 public fixture로 승격하지 않는다. public-safe synthetic fixture로 재작성한다.
- CDN React/Babel wiring은 prototype host로만 본다. 실제 사용 방식은 사용자 소유 HTML building block 정책 또는 local/offline packaging 결정 후 확정한다.
- CSS/HTML building block 자체는 사용자가 소유한다. agent는 임의로 visual block을 새로 만들지 않고, schema/payload/validation/CLI integration만 제공한다.
- `tweaks-panel.jsx`의 edit-mode protocol은 참고하되, runtime 필수 기능으로 강제하지 않는다. 디자인 조정용 optional dev aid로 분리한다.

### Official Building Block Catalog
구현 단계에서 다음 building block 이름을 공식 catalog로 승격한다. HTML/CSS 구현은 사용자 소유지만, agent/runtime은 이 이름과 payload shape만 사용한다.

| Block | Prototype source | Agent-owned contract | User-owned visual |
| --- | --- | --- | --- |
| `SidePanelShell` | `panel.jsx`, `styles.css` | width/height range, scroll behavior, theme metadata | shell CSS, border, shadow, radius |
| `PanelChrome` | `panel.jsx` | title/status fields | dot/live/chrome styling |
| `PanelHeader` | `panel.jsx` | `entity_ref`, `title`, `subtitle`, `privacy_level`, `generated_at`, `schema_version` | typography/spacing |
| `WarningBanner` | `panel.jsx`, `sections.jsx` | `warnings[]` object schema | warning color, icon, surface |
| `SummaryBlock` | `sections.jsx` | `summary` section schema | summary text styling |
| `MetricGrid` | `sections.jsx` | metric item schema, tone enum | grid/hero metric styling |
| `EntityList` | `sections.jsx` | entity item schema, `entity_ref` requirement | avatar/list/badge styling |
| `Timeline` | `sections.jsx` | timeline item schema, state enum | dot/line/timeline styling |
| `TaskList` | `sections.jsx` | task item schema, intent policy | checkbox/list styling |
| `ActionGroup` | `sections.jsx` | action intent/approval/dry-run schema | button styling |
| `SourceCommandsFooter` | `panel.jsx` | provenance object schema | monospace footer styling |
| `ViewTabs` | `app.jsx` | view registry ids/labels/icons | tab UI styling |
| `ThemeTokens` | `styles.css`, `app.jsx` | allowed token axes and ranges | exact color/spacing implementation |
| `TweaksPanel` | `tweaks-panel.jsx` | optional dev/design aid only | tweak UI implementation |

### No-from-scratch Generation Rule
Agent는 다음 작업을 직접 하면 실패다.
- 새 standalone side-panel HTML 파일을 즉흥 생성.
- registered block에 없는 section type을 임의 생성.
- payload schema 없이 CSS/HTML부터 작성.
- source command/provenance 없는 운영 패널 생성.
- action button을 approval/dry-run policy 없이 생성.
- user-owned CSS/HTML building block을 agent 판단으로 재설계.

허용되는 작업:
- registered block이 요구하는 JSON payload 생성.
- `side-panel payload validate`로 payload 검증.
- `side-panel view draft`로 새 view proposal 생성.
- 새 block/view가 필요할 때 implementation이 아니라 `docs/side-panel-design-reference.md`와 memory/decision record에 proposal로 남김.
- 사용자가 제공한 HTML/CSS building block을 adapter로 연결할 계획 작성.

### 계획 보강 결정
- 기존 `docs/side-panel.md`는 단순 방향 문서가 아니라 **사용자 제공 prototype 기반 design reference**를 담는다.
- `docs/side-panel-payload-schema.md`는 zip의 `data.jsx` contract를 기준으로 확장한다.
- `side-panel spec --json`은 supported views, section types, variant recommendation, token axes, privacy fields, source command requirements를 반환한다.
- `side-panel payload build`는 HTML을 만들지 않고, 위 design contract가 소비할 JSON payload만 만든다.
- visual QA는 HTML 구현 이후 `screenshots/*.png`를 golden reference로 삼되, private data가 없는 synthetic payload로만 수행한다.

## Proposed CLI Surface
### DB Namespace
```powershell
chat-lms db init --profile <name> --template academy-basic --json
chat-lms db inspect --profile <name> --json
chat-lms db schema show --profile <name> --json
chat-lms db schema diff --profile <name> --from <version> --to <version> --json
chat-lms db migrate plan --profile <name> --to <version> --json
chat-lms db migrate apply --profile <name> --plan <plan-id> --require-backup --json
chat-lms db query list --profile <name> --json
chat-lms db query run --profile <name> --name attendance_today --params params.json --json
chat-lms db backup create --profile <name> --reason "<reason>" --json
chat-lms db restore plan --profile <name> --backup <id> --json
chat-lms db doctor --profile <name> --json
```

### Academy Namespace
DB가 raw table 중심이 되지 않도록, 반복 운영은 domain command로 감싼다.

```powershell
chat-lms academy class list --profile <name> --json
chat-lms academy class show --profile <name> --class-id <id> --json
chat-lms academy learner find --profile <name> --query "<name-or-token>" --json
chat-lms academy lesson record --profile <name> --class-id <id> --date 2026-06-08 --dry-run --json
chat-lms academy attendance summary --profile <name> --class-id <id> --range this-week --json
chat-lms academy homework status --profile <name> --class-id <id> --json
```

### Side Panel Namespace
보조 패널은 HTML/CSS를 생성하는 도구가 아니라, 우선 **검증된 payload와 view inventory**를 제공하는 도구다.

```powershell
chat-lms side-panel spec --json
chat-lms side-panel view list --profile <name> --json
chat-lms side-panel payload build --profile <name> --view class_overview --entity class:<id> --json
chat-lms side-panel payload validate --from payload.json --json
chat-lms side-panel doctor --profile <name> --json
```

## Structured State
### DB Schema Registry
필수 필드:
- `schema_id`
- `version`
- `domain`
- `tables`
- `indexes`
- `migration_history`
- `named_queries`
- `created_by_tool`
- `evidence_refs`
- `privacy_level`

### Named Query Registry
필수 필드:
- `query_name`
- `summary`
- `domain`
- `inputs_schema`
- `output_schema`
- `sql_or_adapter_ref`
- `safety_level`
- `side_panel_compatible`
- `tests`
- `examples`

### Memory / Decision Record
현재 free text 중심 memory를 다음 구조로 확장한다.

필수 필드:
- `key`
- `scope`: `workspace`, `profile`, `class`, `learner`, `tool`, `schema`, `side_panel`
- `summary`
- `entity_ref`
- `source`
- `evidence_refs`
- `updated_at`
- `expires_at`
- `privacy_level`
- `reason`

### 보조 패널 Payload Contract
CSS/HTML 구현은 제외하지만, payload contract는 반드시 정의한다. 이 contract는 사용자 제공 HTML prototype의 `data.jsx`/`panel.jsx` 구조를 기준으로 한다.

필수 top-level 필드:
- `schema_version`
- `view_id`
- `title`
- `subtitle`
- `entity_ref`
- `generated_at`
- `privacy_level`
- `sections`
- `warnings`
- `source_commands`

선택 top-level 필드:
- `recommended_variant`: `a`, `b`, `c` 중 하나. 없으면 view registry 기본값을 사용한다.
- `design_tokens`: `accent`, `fontSize`, `density`, `round`, `theme` override. private runtime에서만 저장하고 public fixture에는 synthetic 값만 둔다.
- `actions`: legacy/adapter 호환용. 신규 payload는 `action_group` section을 우선한다.

필수 section type:
- `summary`
- `metric_grid`
- `entity_list`
- `timeline`
- `task_list`
- `action_group`

View registry 기본값:
- `class_overview`: variant `b`, metric hero 우선.
- `learner_detail`: variant `a`, warning/summary/timeline 우선.
- `attendance_summary`: variant `b`, 출석률/예외 출결 metric 우선.
- `session_record`: variant `c`, timeline/action 우선.
- `homework_status`: variant `a`, entity list/task list 우선.

Validation 규칙:
- `warnings`는 top-level list이며 header 직후 렌더될 수 있어야 한다.
- production `payload build` 결과는 `source_commands`를 1개 이상 반드시 포함한다. hand-authored fixture validation에서는 누락을 warning으로 허용하되 `doctor`가 provenance warning을 보고한다.
- 모든 action은 `label`, `intent`, `requires_approval`, `dry_run_default`를 가져야 한다. 버튼 label만 있는 action은 implementation 단계에서 reject한다.
- `task_list`의 check state는 local UI state일 수 있지만, 실제 운영 상태 변경은 CLI action intent로만 수행한다.

### 90% Design Compliance Checklist
`docs/side-panel-design-reference.md`는 zip-derived trait를 `required`, `recommended`, `optional`, `out_of_scope`로 분류해야 한다. 구현 완료 판단은 `required` 항목 100%, `recommended` 항목 80% 이상 충족으로 한다. 이것을 사용자 표현인 “디자인적인 것들 적극(90프로) 활용”의 실행 기준으로 삼는다.

Required:
- narrow/tall panel shell: 기본 reference는 372px x 760px 전후.
- panel chrome with `보조 패널 · side-panel` and LIVE/status affordance.
- header metadata: `entity_ref`, `title`, `subtitle`, `privacy_level`, generated time, schema version.
- warning-first rendering immediately below header.
- section renderer supports `summary`, `metric_grid`, `entity_list`, `timeline`, `task_list`, `action_group`.
- source command footer/provenance.
- light/dark token parity.
- view registry for `class_overview`, `learner_detail`, `attendance_summary`, `session_record`, `homework_status`.

Recommended:
- A/B/C variants.
- blue accent default `#3182F6`.
- Pretendard-style Korean UI typography.
- density and roundness token axes.
- metric hero promotion for variant B.
- operation divider style for variant C.

Out of scope:
- copying the raw zip, screenshots, CDN host, Babel dev host, or exact prototype wiring into production without explicit approval.
- agent-authored CSS/HTML visual block invention.

### Detailed JSON Shapes
`source_commands[]` item shape:
```json
{
  "command": "academy class show",
  "args": ["--class-id", "sample-class"],
  "query_name": "class_overview",
  "entity_ref": "class:sample-class",
  "exit_code": 0,
  "ran_at": "2026-06-09T14:20:00+09:00",
  "redaction": "applied"
}
```

`warnings[]` item shape:
```json
{
  "severity": "warn",
  "code": "HOMEWORK_RISK",
  "message": "과제 미제출 3건이 임박한 평가에 영향을 줄 수 있어요.",
  "source": "academy.homework_status",
  "blocking": false,
  "action_intent": "homework.review"
}
```

`summary` section shape:
```json
{ "type": "summary", "text": "요약 문장", "tone": "neutral" }
```

`metric_grid` section shape:
```json
{
  "type": "metric_grid",
  "items": [
    { "label": "출석률", "value": "94", "unit": "%", "delta": "+2", "tone": "up" }
  ]
}
```

`entity_list` section shape:
```json
{
  "type": "entity_list",
  "title": "주의가 필요한 학생",
  "items": [
    {
      "entity_ref": "learner:sample-1",
      "name": "샘플 학생",
      "meta": "과제 확인 필요",
      "badge": "과제",
      "tone": "warn",
      "initial": "샘"
    }
  ]
}
```

`timeline` section shape:
```json
{
  "type": "timeline",
  "title": "최근 수업",
  "items": [
    { "time": "6/9", "title": "수업 기록", "meta": "출석 10", "state": "done" }
  ]
}
```

`task_list` section shape:
```json
{
  "type": "task_list",
  "title": "오늘 할 일",
  "items": [
    {
      "text": "결석 사유 확인",
      "done": false,
      "intent": "attendance.request_absence_reason",
      "requires_approval": true
    }
  ]
}
```

`action_group` section shape:
```json
{
  "type": "action_group",
  "actions": [
    {
      "label": "출결 입력",
      "intent": "attendance.record",
      "primary": true,
      "requires_approval": true,
      "dry_run_default": true
    }
  ]
}
```

Allowed values:
- `privacy_level`: `workspace`, `profile`, `class`, `learner`, `tool`, `schema`, `side_panel`
- `tone`: `neutral`, `good`, `warn`, `up`, `down`, `flat`
- `severity`: `info`, `warn`, `danger`
- timeline `state`: `done`, `good`, `miss`, `pending`
- `design_tokens.accent`: hex color matching `^#[0-9A-Fa-f]{6}$`
- `design_tokens.fontSize`: integer `13..18`
- `design_tokens.density`: `compact`, `comfy`, `roomy`
- `design_tokens.round`: `sharp`, `soft`, `round`
- `design_tokens.theme`: `light`, `dark`, `system`

### View-to-Query Mapping
`side-panel payload build` must not guess data dependencies. Each view maps to named queries and default sections.

| View | Entity | Default variant | Required named queries | Required sections |
| --- | --- | --- | --- | --- |
| `class_overview` | `class:<id>` | `b` | `class_overview`, `class_attention_list`, `class_recent_sessions`, `class_today_tasks` | `summary`, `metric_grid`, `entity_list`, `timeline`, `task_list`, `action_group` |
| `learner_detail` | `learner:<id>` | `a` | `learner_profile`, `learner_metrics`, `learner_timeline`, `learner_coaching_tasks` | `summary`, `metric_grid`, `timeline`, `task_list`, `action_group` |
| `attendance_summary` | `class:<id>` | `b` | `attendance_summary`, `attendance_exceptions`, `attendance_session_timeline` | `summary`, `metric_grid`, `entity_list`, `timeline`, `action_group` |
| `session_record` | `session:<id>` | `c` | `session_record`, `session_flow`, `session_followups` | `summary`, `metric_grid`, `timeline`, `task_list`, `action_group` |
| `homework_status` | `class:<id>` | `a` | `homework_status`, `homework_risk_learners`, `homework_followups` | `summary`, `metric_grid`, `entity_list`, `task_list`, `action_group` |

### Refresh / Staleness Lifecycle
- `payload build` writes no persistent snapshot by default; it returns JSON.
- Optional private snapshot caching is allowed only under private profile workspace.
- Payload is `fresh` for 5 minutes by default, unless the source named query marks a shorter TTL.
- Any DB migration, academy write, memory upsert affecting the same `entity_ref`, or hook closeout obligation invalidates cached payloads for that entity.
- `side-panel payload build --refresh` bypasses cache.
- `side-panel doctor` reports stale cached payloads but never rebuilds them without explicit command.

### Error Contract
All side-panel commands use existing harness exit-code semantics.

| Error | Exit | JSON code |
| --- | --- | --- |
| unknown view | `2` | `UNKNOWN_SIDE_PANEL_VIEW` |
| missing entity | `2` | `MISSING_ENTITY_REF` |
| invalid payload shape | `2` | `INVALID_SIDE_PANEL_PAYLOAD` |
| named query failure | query exit code or `2` | `SIDE_PANEL_SOURCE_QUERY_FAILED` |
| unsafe/public profile root | `4` | `PUBLIC_REPO_STATE_REJECTED` |
| privacy/redaction violation | `4` | `SIDE_PANEL_PRIVACY_VIOLATION` |
| unresolved side-panel memory obligation | `5` | `SIDE_PANEL_MEMORY_REQUIRED` |

### Context Hydration Shape
`context hydrate --for-codex --json` must include:
```json
{
  "side_panel": {
    "official_name": "보조 패널(side panel)",
    "views": ["class_overview", "learner_detail", "attendance_summary", "session_record", "homework_status"],
    "section_types": ["summary", "metric_grid", "entity_list", "timeline", "task_list", "action_group"],
    "design_reference": "user-provided-html-prototype",
    "user_owned_html_css": true
  }
}
```

### Memory Migration Rule
Existing memory entries with only `key`, `scope`, and `text` remain readable. When a command touches the entry, it upgrades the record by adding `summary`, `entity_ref`, `source`, `evidence_refs`, `updated_at`, `privacy_level`, and `reason`. Migration must not rewrite all private memory during read-only hydration.

## Public / Private Boundary
### Public Repo에 들어갈 것
- CLI source code
- DB schema templates
- migration templates
- public-safe sample fixtures
- named query definitions with fake data only
- side-panel payload schema
- side-panel Markdown guideline skeleton
- side-panel design reference summary derived from the user prototype
- tests and docs

### Private Profile Workspace에만 들어갈 것
- 실제 DB 파일
- 실제 학생/학부모/수업 데이터
- 실제 generated report
- 실제 보조 패널 payload snapshot
- 실제 backup
- private memory
- external account state

### 강제 규칙
- `db init`은 public repo에 DB를 만들면 exit code `4`로 실패한다.
- `db migrate apply`는 backup 없이는 실패한다.
- 실제 write 작업은 기본 `--dry-run` 또는 explicit approval gate를 요구한다.
- Stop hook은 schema/tool/query/side-panel 변경 후 memory/decision record가 없으면 exit code `5`로 막는다.
- 사용자 제공 HTML zip 원본, screenshot, prototype source를 public repo에 그대로 추가하려면 별도 승인과 privacy scan이 필요하다. 계획 단계에서는 디자인 특성만 문서화한다.

## Execution Waves
### Agent Ownership Rule
각 wave 실행 전에는 반드시 다음 두 역할을 분리한다.
- Coding Agent: 해당 wave의 production code/docs/test fixture 구현 담당.
- QA/Testing Agent: Coding Agent와 독립적으로 tests, privacy scan, CLI QA transcript, side-panel payload validation을 검수.

각 wave는 시작 전에 development plan, test plan, success criteria, failure criteria를 wave note에 남긴다. 새 test module을 계획에서 언급했다면, 해당 wave의 첫 production 작업 전에 그 test module을 먼저 만든다.

### Parser / Dispatcher Rule
새 CLI namespace나 command를 추가하는 모든 wave는 다음을 한 task로 묶는다.
- `src/chat_lms_agent/command_parser.py` parser registration
- command dispatcher registration
- invalid flag/unknown subcommand test
- `--json` error contract test
- `--help` output test

### Side-panel No-copy Rule
사용자 제공 prototype은 design reference다. raw zip, screenshots, CDN dev host, exact generated HTML/CSS를 public repo에 넣는 작업은 별도 승인 없이는 실패로 간주한다. 구현 wave는 대신 public-safe synthetic fixture와 textual design checklist를 만든다.

### Side-panel No-from-scratch Gate
보조 패널 관련 구현은 다음 순서를 반드시 따른다.
1. `side-panel spec --json`에 block/view/section이 등록되어 있는지 확인한다.
2. 등록되어 있지 않으면 HTML/CSS를 만들지 않고 `side-panel view draft` 또는 `side-panel block proposal`만 만든다.
3. proposal은 `docs/side-panel-design-reference.md`, memory/decision record, test plan을 포함해야 한다.
4. payload schema와 validator test가 RED -> GREEN 된 뒤에만 renderer/user-owned HTML integration을 논의한다.
5. Stop hook은 active side-panel view/block proposal이 memory/decision record 없이 남아 있으면 exit code `5`로 차단한다.

실패 조건:
- `*.html`, `*.css`, `*.jsx`, `*.tsx`에서 side-panel UI를 새로 만들었는데 `side-panel spec`/design reference/test가 없다.
- `sections[]`에 unknown type이 들어간다.
- `source_commands`가 없는 production payload가 생성된다.
- action이 `intent`, `requires_approval`, `dry_run_default` 없이 생성된다.
- user-owned visual block을 agent가 독자적으로 redesign한다.

테스트 gate:
- `tests/test_side_panel_no_from_scratch.py::test_unknown_section_requires_block_proposal`
- `tests/test_side_panel_no_from_scratch.py::test_new_view_requires_design_reference_and_memory_record`
- `tests/test_side_panel_no_from_scratch.py::test_production_payload_requires_source_command_provenance`
- `tests/test_side_panel_no_from_scratch.py::test_actions_require_intent_approval_and_dry_run_policy`
- `tests/test_repo_privacy.py::test_raw_side_panel_html_css_is_not_added_without_approval_marker`


## Wave 0. Reference Pinning + Terminology Lock
목표: golden standard와 용어를 검증 가능한 문서로 고정한다.

작업:
- `docs/golden-standards.md` 작성
- `docs/terminology.md` 작성
- 기존 문서의 `right panel`, `우측패널` 표현을 `보조 패널(side panel)`로 migration하는 task 정의
- golden standard source가 없는 경우 `assumption`으로 기록하고 구현 gate에서 차단

테스트:
- `tests/test_docs_contract.py::test_side_panel_is_the_only_official_panel_name`
- `tests/test_docs_contract.py::test_golden_standards_have_sources_or_assumption_markers`

Manual QA:
```powershell
uv run pytest tests/test_docs_contract.py -q
rg -n "right panel|우측패널|assistant panel" docs plans README.md AGENTS.md
```

완료 기준:
- 공식 용어가 하나로 고정된다.
- golden standard 참조 방식이 code-copy가 아니라 trait checklist임이 문서화된다.

## Wave 1. Current Harness Baseline Audit
목표: 현재 flat module 기반 v1 구현과 미래 module boundary를 연결한다.

작업:
- `docs/current-harness-baseline.md` 작성
- 현재 command tree, memory/tool 기능, hook 기능, runtime boundary를 code reference로 정리
- 기존 계획의 stale assumption을 새 계획에서 재사용하지 않도록 marking
- `commands.py` flat 구조를 유지할지, `commands/` package로 나눌지 decision record 작성

테스트:
- `tests/test_docs_contract.py::test_current_baseline_mentions_live_command_tree`
- `tests/test_docs_contract.py::test_stale_plan_assumptions_are_not_authoritative`

Manual QA:
```powershell
uv run python -m chat_lms_agent --help
uv run python -m chat_lms_agent context hydrate --for-codex --json
```

완료 기준:
- 구현자가 이전 계획의 오래된 실패 상태를 현재 사실로 오해하지 않는다.

## Wave 2. DB Runtime Boundary + Schema Registry
목표: DB를 매번 새로 만들지 않고, private profile 안에서 versioned schema로 운영하게 만든다.

작업:
- `chat-lms db inspect`
- `chat-lms db schema show`
- `chat-lms db schema diff`
- `chat-lms db init --template academy-basic`
- public-safe schema fixture 추가
- private profile DB root resolver 추가
- DB root가 public repo면 exit code `4`

테스트:
- `tests/test_db_boundary.py::test_db_root_inside_public_repo_is_rejected`
- `tests/test_db_schema_registry.py::test_academy_basic_schema_is_versioned`
- `tests/test_db_schema_registry.py::test_schema_inspect_uses_temp_profile_only`

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-db-wave2"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent db schema show --profile-root $root --json
uv run python -m chat_lms_agent db init --profile-root . --template academy-basic --json
```

완료 기준:
- DB 생성/검사는 private/temp profile에서만 가능하다.
- public repo에 real DB가 생기지 않는다.

## Wave 3. Migration, Backup, Restore, Rollback Gates
목표: DB 수정이 임의 실행이 아니라 plan -> backup -> apply -> memory 기록 흐름을 따른다.

작업:
- `db migrate plan`
- `db migrate apply --require-backup`
- `db backup create`
- `db restore plan`
- migration journal 작성
- migration이 memory/decision obligation을 생성하게 함
- Stop hook이 migration 후 memory 없으면 exit code `5`

테스트:
- `tests/test_db_migration.py::test_migration_apply_requires_backup`
- `tests/test_db_migration.py::test_migration_plan_does_not_modify_db`
- `tests/test_session_closeout.py::test_closeout_blocks_schema_change_without_decision_record`

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-db-wave3"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent db migrate plan --profile-root $root --to next --json
uv run python -m chat_lms_agent db migrate apply --profile-root $root --to next --json
uv run python -m chat_lms_agent db backup create --profile-root $root --reason "qa migration" --json
uv run python -m chat_lms_agent db migrate apply --profile-root $root --to next --require-backup --json
```

완료 기준:
- 어떤 DB write도 plan/backup/decision 없이 조용히 실행되지 않는다.

## Wave 4. CLI-first Named Query Layer
목표: 에이전트가 DB를 직접 뒤지는 대신, 빠르고 재사용 가능한 query CLI를 사용한다.

작업:
- `db query list`
- `db query show`
- `db query run`
- named query registry 작성
- query input/output schema validation
- query result redaction
- query 실행 결과가 보조 패널 payload source가 될 수 있게 `side_panel_compatible` 필드 추가

테스트:
- `tests/test_named_queries.py::test_query_list_returns_sorted_inventory`
- `tests/test_named_queries.py::test_query_run_validates_required_params`
- `tests/test_named_queries.py::test_query_output_is_redacted_before_json`

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-query-wave4"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent db query list --profile-root $root --json
uv run python -m chat_lms_agent db query run --profile-root $root --name class_overview --params tests/fixtures/db/class_overview_params.json --json
```

완료 기준:
- 반복 조회는 CLI로 가능하다.
- 구현자는 raw DB open/grep을 기본 경로로 사용하지 않는다.

## Wave 5. Academy Domain Commands
목표: 학원 운영에서 자주 쓰는 작업을 DB table이 아니라 domain command로 노출한다.

v1 기본 workflow:
- class overview
- learner lookup
- lesson/session record dry-run
- attendance summary
- homework status

v1 제외:
- 결제 실거래 write
- 학부모 메시지 실제 발송
- 외부 LMS write

작업:
- `academy class list/show`
- `academy learner find`
- `academy attendance summary`
- `academy homework status`
- `academy lesson record --dry-run`
- domain command가 내부적으로 named query/action template을 호출하게 함

테스트:
- `tests/test_academy_commands.py::test_class_overview_uses_named_query`
- `tests/test_academy_commands.py::test_learner_find_rejects_ambiguous_private_search_without_profile`
- `tests/test_academy_commands.py::test_lesson_record_defaults_to_dry_run`

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-academy-wave5"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent academy class list --profile-root $root --json
uv run python -m chat_lms_agent academy attendance summary --profile-root $root --class-id sample-class --range this-week --json
```

완료 기준:
- 학원 운영 반복 작업이 CLI-first로 고정된다.
- 에이전트는 “무슨 조회가 필요한지” 판단하고 “어떻게 조회할지”는 CLI에 맡긴다.

## Wave 6. Structured Memory + Hook Obligations
목표: DB/query/tool/보조 패널 변경이 세션 간 사라지지 않게 한다.

작업:
- memory schema 확장
- decision record schema 추가
- `memory upsert`에 `--entity-ref`, `--reason`, `--evidence`, `--privacy-level` 추가
- DB schema/query/tool/side-panel change가 obligation을 생성하게 함
- Stop hook이 obligation 미해결 시 exit code `5`
- SessionStart/context hydrate가 DB schema snapshot, query inventory, side-panel view inventory를 포함

테스트:
- `tests/test_memory_registry.py::test_schema_change_requires_decision_record`
- `tests/test_memory_registry.py::test_side_panel_view_memory_is_scoped`
- `tests/test_context_hydration.py::test_hydrate_includes_db_and_side_panel_inventory`
- `tests/test_hooks.py::test_stop_hook_blocks_unresolved_db_obligation`

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-memory-wave6"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent session closeout --profile-root $root --verify-memory --json
uv run python -m chat_lms_agent memory upsert --profile-root $root --key schema:academy-basic --scope schema --text "academy-basic schema initialized" --json
uv run python -m chat_lms_agent context hydrate --profile-root $root --for-codex --json
```

완료 기준:
- 새 세션은 사용 가능한 DB/query/보조 패널 도구를 자동으로 안다.
- 변경 후 memory 누락 상태로 조용히 종료되지 않는다.

## Wave 6.5. 보조 패널 Prototype-to-Spec 승격
목표: 사용자 제공 HTML prototype을 그대로 복사하지 않고, from-scratch 생성을 막는 공식 design reference, block catalog, validator contract로 승격한다.

작업:
- `docs/side-panel-design-reference.md` 작성
- `docs/side-panel-building-block-catalog.md` 작성
- `docs/side-panel-user-owned-html-css.md` 작성
- `side-panel spec --json`의 초기 fixture 작성
- `side-panel block list --json` 계획 추가
- `side-panel view draft --from-prototype <view>` 계획 추가
- prototype-derived block을 `required`, `recommended`, `optional`, `out_of_scope`로 분류
- `No-from-scratch Generation Rule`을 docs와 tests에 반영
- raw zip, screenshot, prototype source를 public repo에 넣지 않는 no-copy privacy rule 추가

각 문서의 역할:
- `docs/side-panel-design-reference.md`: 사용자가 준 HTML prototype의 디자인 DNA와 90% compliance checklist.
- `docs/side-panel-building-block-catalog.md`: `SidePanelShell`, `PanelChrome`, `PanelHeader`, `WarningBanner`, `SummaryBlock`, `MetricGrid`, `EntityList`, `Timeline`, `TaskList`, `ActionGroup`, `SourceCommandsFooter`, `ViewTabs`, `ThemeTokens`, `TweaksPanel`.
- `docs/side-panel-user-owned-html-css.md`: 사용자가 CSS/HTML building block을 제공하는 방식, agent가 건드릴 수 없는 영역, adapter가 받아야 하는 JSON.

테스트:
- `tests/test_side_panel_design_reference.py::test_zip_derived_required_blocks_are_documented`
- `tests/test_side_panel_design_reference.py::test_design_reference_defines_required_recommended_optional_out_of_scope`
- `tests/test_side_panel_design_reference.py::test_user_owned_html_css_boundary_is_explicit`
- `tests/test_side_panel_no_from_scratch.py::test_unknown_block_creates_proposal_not_html`
- `tests/test_side_panel_no_from_scratch.py::test_raw_prototype_files_are_not_required_public_artifacts`
- `tests/test_context_hydration.py::test_hydrate_names_user_owned_side_panel_contract`

Manual QA:
```powershell
uv run pytest tests/test_side_panel_design_reference.py tests/test_side_panel_no_from_scratch.py -q
uv run python -m chat_lms_agent side-panel spec --json
uv run python -m chat_lms_agent context hydrate --for-codex --json
```

완료 기준:
- 제공 zip에 있는 디자인/블록 요소가 공식 문서와 spec으로 해석되어 있다.
- 구현자는 새 HTML을 만들기 전에 반드시 block/view registry를 확인해야 한다.
- 새 view/block이 필요하면 구현이 아니라 proposal + memory/decision record가 먼저 생긴다.
- agent가 CSS/HTML을 즉흥 생성하는 경로가 tests/doctor/hook에서 차단된다.

## Wave 7. 보조 패널(side panel) Contract + User-owned Design Guide
목표: 사용자가 제공한 HTML prototype의 디자인 특성을 보조 패널 기준으로 고정하고, 사용자가 직접 CSS/HTML building blocks를 만들 수 있도록 agent/runtime 쪽 contract와 경계만 확정한다.

작업:
- `docs/side-panel.md` 작성
- `docs/side-panel-payload-schema.md` 작성
- `docs/side-panel-design-reference.md` 작성
- 사용자 제공 prototype의 design DNA를 문서화: 372px x 760px 전후 narrow/tall shell, panel chrome, LIVE indicator, header metadata, warning-first flow, source command footer, light/dark token parity, A/B/C variants
- `chat-lms side-panel spec`
- `chat-lms side-panel view list`
- `chat-lms side-panel payload build`
- `chat-lms side-panel payload validate`
- 보조 패널 view registry 작성
- payload privacy/redaction 검사
- `class_overview`, `learner_detail`, `attendance_summary`, `session_record`, `homework_status`를 v1 required view로 고정
- supported section을 `summary`, `metric_grid`, `entity_list`, `timeline`, `task_list`, `action_group`로 고정
- top-level `warnings`와 `source_commands`를 보조 패널 provenance/operation trace로 고정
- action button은 직접 write가 아니라 `action intent`로만 표현하고, 실행은 CLI approval/dry-run gate에 맡김
- CSS/HTML 구현 영역을 `USER-OWNED`로 명시

보조 패널 설계 방향:
- 세로로 긴 Codex Desktop 보조 패널을 기본 전제로 한다.
- 한 화면에서 class/learner/session 상태를 빠르게 scan할 수 있어야 한다.
- 카드 남발이 아니라 compact section과 list 중심으로 구성한다.
- visual 구현은 사용자의 building block guideline을 따른다.
- agent는 HTML을 즉흥 생성하지 않고, 검증된 payload를 제공한다.
- HTML/CSS block은 payload schema를 소비하는 presentation layer다.
- 기본 aesthetic은 Toss-like operational panel이다: 밝은 surface, 부드러운 border/shadow, blue accent, 명확한 metric typography, low-noise warning color, compact list/timeline.
- variant A/B/C는 삭제하지 않는다. view마다 recommended variant를 갖고, 사용자가 CSS/HTML building block에서 최종 시각 구현을 조정할 수 있게 한다.
- dark mode는 별도 테마가 아니라 같은 정보 구조를 유지하는 token alternate다.
- tweak controls는 dev/design aid로만 취급한다. runtime 필수 UX가 아니다.

테스트:
- `tests/test_side_panel_contract.py::test_side_panel_payload_schema_requires_privacy_level`
- `tests/test_side_panel_contract.py::test_side_panel_payload_rejects_unknown_section_type`
- `tests/test_side_panel_contract.py::test_side_panel_view_list_is_hydrated_into_context`
- `tests/test_side_panel_contract.py::test_required_views_match_design_reference`
- `tests/test_side_panel_contract.py::test_action_group_requires_intent_and_approval_policy`
- `tests/test_side_panel_contract.py::test_source_commands_are_preserved_for_provenance`
- `tests/test_side_panel_contract.py::test_spec_returns_variant_and_token_axes`
- `tests/test_side_panel_contract.py::test_section_schemas_match_design_reference`
- `tests/test_side_panel_contract.py::test_design_token_values_are_validated`
- `tests/test_side_panel_contract.py::test_payload_build_maps_views_to_named_queries`
- `tests/test_side_panel_contract.py::test_payload_cache_staleness_and_refresh_policy`
- `tests/test_side_panel_contract.py::test_side_panel_error_contract_codes`
- `tests/test_context_hydration.py::test_hydrate_includes_side_panel_contract_shape`
- `tests/test_memory_registry.py::test_legacy_memory_is_readable_before_side_panel_upgrade`
- `tests/test_repo_privacy.py::test_raw_side_panel_zip_and_screenshots_are_not_committed_without_approval`
- `tests/test_repo_privacy.py::test_side_panel_fixtures_are_public_safe`

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-side-panel-wave7"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent side-panel spec --json
uv run python -m chat_lms_agent side-panel view list --profile-root $root --json
uv run python -m chat_lms_agent side-panel payload build --profile-root $root --view class_overview --entity class:sample-class --json
uv run python -m chat_lms_agent side-panel payload validate --from tests/fixtures/side_panel/class_overview_payload.json --json
```

Conditional visual QA:
- If the user explicitly approves the local prototype as a visual reference during implementation, run browser visual checks against the user-owned HTML/CSS using synthetic payload only.
- If approval is not present, do not commit or depend on screenshot files. Use `docs/side-panel-design-reference.md` checklist plus payload schema tests as public acceptance evidence.

완료 기준:
- 보조 패널 명칭과 payload contract가 고정된다.
- 사용자 제공 HTML prototype의 디자인 특성이 `docs/side-panel-design-reference.md`에 고정된다.
- 구현자는 새 디자인을 발명하지 않고, prototype의 구조와 visual language를 약 90% 기준으로 삼는다.
- CSS/HTML을 구현하지 않아도, 나중에 사용자가 만들 block이 어떤 데이터를 받아야 하는지 결정된다.
- 보조 패널 payload에는 CLI provenance, privacy level, view id, recommended variant, supported section structure가 포함된다.

## Wave 8. Doctor + QA Evidence Layer
목표: 이 구조가 깨졌을 때 agent가 바로 알 수 있게 한다.

작업:
- `doctor`가 DB root, schema registry, migration journal, named query registry, memory obligations, side-panel payload schema를 검사
- `doctor --repair`는 safe repair만 수행하고 DB write/migration은 하지 않음
- QA capture가 DB/side-panel/manual CLI transcript를 저장

테스트:
- `tests/test_doctor.py::test_doctor_reports_db_registry_status`
- `tests/test_doctor.py::test_doctor_reports_side_panel_schema_status`
- `tests/test_doctor.py::test_doctor_repair_does_not_apply_migrations`

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-doctor-wave8"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent doctor --profile-root $root --json
uv run python -m chat_lms_agent doctor --profile-root $root --repair --json
```

완료 기준:
- DB, memory, query, side-panel, hook 상태를 한 명령으로 진단할 수 있다.

## Wave 9. Final Integration + Regression
목표: 전체 구조가 public-safe이고 새 세션에서 자동으로 기억되는지 검증한다.

테스트:
```powershell
uv run pytest -q
uv run ruff check .
uv run basedpyright
uv run pytest tests/test_repo_privacy.py -q
```

Manual QA:
```powershell
$root = Join-Path $env:TEMP "chat-lms-final"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $root
uv run python -m chat_lms_agent db init --profile-root $root --template academy-basic --json
uv run python -m chat_lms_agent db query list --profile-root $root --json
uv run python -m chat_lms_agent side-panel payload build --profile-root $root --view class_overview --entity class:sample-class --json
uv run python -m chat_lms_agent context hydrate --profile-root $root --for-codex --json
uv run python -m chat_lms_agent session closeout --profile-root $root --verify-memory --json
```

완료 기준:
- public repo에 private DB/report/memory/log가 없다.
- 새 세션 context에 DB/query/tool/side-panel inventory가 들어간다.
- closeout은 누락된 memory/decision obligation을 차단한다.
- CSS/HTML 보조 패널 구현은 여전히 사용자 소유 영역으로 남아 있다.

## Commit Plan
- `docs(standards): pin harness golden standards`
- `docs(terminology): define side panel naming`
- `feat(db): add private schema registry`
- `feat(db): add migration backup gates`
- `feat(query): add named academy queries`
- `feat(academy): add class learner lesson commands`
- `feat(memory): record db and side panel obligations`
- `feat(side-panel): add payload contract commands`
- `feat(doctor): verify db and side panel harness`
- `test(privacy): guard db and side panel fixtures`

## Failure Criteria
- DB file, real learner data, generated report, backup, log, private path, or private memory appears in public repo.
- Any DB write runs without explicit private profile root and backup/approval gate.
- A schema/query/tool/side-panel change can be made without memory/decision record.
- SessionStart does not hydrate available DB/query/side-panel inventory.
- Agent must manually inspect raw DB for a standard class/learner/attendance/homework query.
- 보조 패널 CSS/HTML is implemented by agent despite user ownership boundary.
- Agent creates side-panel HTML/CSS/JSX from scratch instead of using registered block/view contracts or creating a proposal first.
- A new side-panel view/block appears without `docs/side-panel-design-reference.md`, validator tests, and memory/decision record.
- Production side-panel payload lacks `source_commands` provenance.
- Side-panel action lacks `intent`, approval policy, or dry-run default.
- Golden standard references are used as vague vibes instead of pinned source/trait checklist.

## Immediate Next Step
실행을 시작한다면 Wave 0부터 진행한다. 먼저 `docs/golden-standards.md`와 `docs/terminology.md`를 만들고, `보조 패널(side panel)` 명칭과 golden standard trait checklist를 테스트 가능한 문서 계약으로 고정한다.
