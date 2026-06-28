# 메타 하네스 결정화-루프 코어 복구 설계 (#4·#5·#6)

> 상태: **구현 완료 + 독립 QA 통과 (2026-06-27)** — ulw-loop 헤드리스로 STEP1~4 구현; `uv run pytest` 510 passed/1 skipped, ruff/basedpyright 클린, 가드레일 전부 준수. 미커밋. 남은 것 = PHASE 0(교사 실DB 중복 실측). 구현 브리프: `plans/core3-impl-brief.md`
> 작성: 2026-06-27 · 코딩 시작 전 사전 설계 문서 (사용자 룰: 개발 전 설계 필수)
> 검증: 3단 병렬 설계 + 독립 QA 적대 리뷰 (코딩 에이전트 ↔ QA 에이전트 분리)

## 확정된 결정 (2026-06-27, 소유자)

1. **sessions 자연키 = `(class_id, session_date, session_kind)`** — 보강수업/본수업 같은 날 공존 허용.
   → `record-class.json`에 `session_kind` 컬럼/파라미터(default `'main'`)/insert set 추가가 #4의 일부로 들어감.
2. **스케줄러 v1 = dry-run 전용 출하** — 스케줄 잡은 primitive의 dry-run 형태만 실행(외부 쓰기 0).
   `--unattended-execute`와 그에 딸린 복잡성(아래 §5b)은 **post-v1로 연기**.
3. **기존 중복 행 = 리포트 전용** — `index --check`가 중복 줄을 목록으로만 보여줌. 코드가 실 학생 데이터를 자동 삭제하지 않음.
   자동 정리(`dedupe`) 동사는 연기.

미정(리뷰 중): test_results 재기록 멱등 여부(§7-2), #6 로그오프 실행 요구(§7-4, dry-run에선 저위험).

---

## 0. 프레이밍 — 우리가 고치는 것의 고도

`chat_lms_agent`는 **메타 하네스**다. 본업은 모든 워크플로를 직접 출하하는 게 아니라, 교사 승인 아래
**반복 작업을 그 교사 데이터에 맞춘 결정적·안전·멱등·스케줄 가능한 primitive로 "결정화(crystallize)"**
하게 해주는 것이다. 저작 기반(프로파일-로컬 write-action 템플릿/라우트, 선언 DSL, 신뢰 게이트)은
이미 견고하다. **깨진 건 그 위의 결정화 사다리(loop)다.**

이 문서는 사다리의 **코어 3단**을 복구한다. 우리는 **제네릭 메타 능력**만 만들고, `ensure-today` 같은
**도메인 워크플로는 손코딩하지 않는다** — 에이전트가 이 사다리로 직접 만든다.

| # | 단(rung) | 메타 능력 | 깨는 증상 |
|---|---|---|---|
| 4 | 멱등 연산 | 어떤 템플릿이든 자연키 선언 → 안전 재실행, 엔진이 중복을 거부 | 비멱등 INSERT, 중복 세션 |
| 5 | 라우트 전달 | 저작한 라우트/명령이 매 세션 SessionStart로 확실히 발견됨 | 죽은 훅, 명령 전달 안 됨 → free-hand |
| 6 | 스케줄러 | 저작한 결정적 명령을 OS 타이머/달력에 바인딩 (세션 수명주기와 분리) | 스케줄러 전무, "매일 손으로" |

---

## 1. QA 판정 요약 — `go-with-changes`

방향·기반·접점 분석은 견고(코드 file:line으로 검증). 단, **코딩 전 반드시 반영해야 할 차단급 6개**:

1. **[#4 차단] `INSERT OR IGNORE` + `cursor.lastrowid` 무성 오류.** 재실행 시 `lastrowid`가 기존 행 id가
   아니라 0/직전값을 반환 → 의존 `update_stub`이 엉뚱한 `session_id`를 갱신 = *막으려던 그 무성 오기록을 재도입*.
   → **해법: `insert`를 `INSERT OR IGNORE`로 바꾸지 말 것. id를 캡처하는 멱등 스텝은 `op:'ensure'`(SELECT-back)**
   로 강제. `record-class.insert_session` → `op:'ensure'`(match=class_id+session_date+session_kind)로 전환.
2. **[#4 차단] 기존 중복 행 미처리.** 프로덕션 DB는 제품 수명 내내 blind INSERT를 써서 **이미 중복 세션이 거의 확실히 존재**
   → 첫 `CREATE UNIQUE INDEX`가 `INDEX_BUILD_CONFLICT`로 실패 → 루그 전체가 실DB에서 무력.
   → **해법: 중복 조사를 #4 범위 안으로 — 단 리포트 전용(소유자 결정 2026-06-27).** `index --check`가 충돌 행그룹을
   목록으로만 보여주고, 정리는 교사가 결정. 코드 자동 삭제 없음.
3. **[#4 차단] `session_kind` 불일치.** 라이브 스키마엔 `session_kind`가 있는데(`_active_on`이 `='main'` 필터로 증명)
   `record-class.json` columns/set엔 없음 → 제안한 자연키 컬럼셋이 템플릿이 쓸 수 있는 것과 불일치.
   → **해법: `session_kind`를 columns/param(default `main`)/set에 추가 후 자연키 선언, 또는 자연키를 (class_id, session_date)로
   좁히고 보강수업 충돌을 교사가 명시 수용.**
4. **[#6 차단] 반복 작업 vs 일회성 승인 모델 모순.** 기존 `consume_approval`은 1회 소비 → 반복 잡이면 1번 뒤 영구 BLOCK.
   → **해법: "standing(상시) 승인" 스코프를 명시 설계** — 소비되지 않되 `job_id`(콘텐츠 해시) 변경/명시 revoke 시 무효. `approvals.py`에 `approval_is_standing`/`revoke_standing` + 테스트.
5. **[#6 차단] "세션 없이도 실행"이 미검증 + 프로파일 루트 추론 위험.** 로그오프 시 실행 여부 미확인; 래퍼가 설치 위치로
   `CHAT_LMS_AGENT_PROFILE_ROOT`를 추론 → 다른 SID/cwd로 실행되면 **다른 교사 DB에 기록**.
   → **해법: 생성된 작업에 프로파일 루트를 명시 핀(env/인자), 추론 금지.** 로그오프 동작 실측·정직 문서화. OS 작업 등록은
   교사에게 명확한 승인 UX(plan_id 바인딩만으론 불충분).
6. **[교차 차단] 무인 execute 잡은 #4 멱등성이 하드 전제.** 미멱등 템플릿을 무인 반복 실행하면(Task Scheduler 재시도/DST/누락보정)
   무인 중복 기록. → **해법: `schedule register --unattended-execute`는 바인딩 템플릿의 UNIQUE 인덱스 PRESENT를
   `index --check`로 검증해야만 허용. v1은 기본 dry-run만.**

비차단(필수): PowerShell argv는 `-File`+argv 배열(적대 입력 테스트), `registered_events`는 모양 변경 대신 키 추가,
쓰기형 팩의 `must_not`은 비-droppable, 11k→13k 전역 상한 인상 최소화·기록, 예외/동시성/경계 테스트 대폭 보강.

### dry-run-only v1 결정이 차단급에 미치는 영향

스케줄러 v1을 dry-run 전용으로 출하하기로 했으므로(외부 쓰기 경로 없음):

- **차단 #4(standing 승인) → post-v1 연기.** dry-run 잡은 `register` 시 작업 생성 1회 승인이면 충분(매 실행 승인 불필요,
  외부 쓰기 0). standing-vs-consume 트레이드오프는 `--unattended-execute`가 들어오는 시점에 설계.
- **차단 #6(execute는 #4 멱등 전제) → post-v1 연기.** v1엔 execute 잡 자체가 없음. 단 §6 교차 불변식①은 execute 도입 시 부활.
- **차단 #5(프로파일 루트 명시 핀) → v1에 그대로 유지.** dry-run 잡도 래퍼를 돌려 프로파일 루트를 해석하므로(엉뚱한 프로파일의
  DB를 *읽을* 위험), 작업 액션에 루트 명시 핀은 v1 필수. 로그오프 *실행* 여부는 dry-run이라 저위험이나 "실제로 도는가"는 실측 권장.
- **차단 #1·#2·#3(#4 관련) → 전부 v1 필수 유지** (스케줄러와 무관, 안전 토대).

---

## 2. 구현 순서 (안전 의존성 방향)

```
PHASE 0  실데이터 조사 (read-only)   ← 반드시 먼저, 사설 DB 필요
PHASE 1  Rung #4  멱등 + 인덱스 + dedupe + lastrowid 수정   (안전 토대)
PHASE 2  Rung #5  SessionStart 명령 인덱스 전달 + 오도 제거   (DB 무위험)
PHASE 3  Rung #6  스케줄러 (FakeBackend 우선, execute는 #4 게이트)
```

**PHASE 0가 핵심 신규 단계(QA 추가).** 자연키를 확정하기 전에, 빌드한 read-only `write-action index --check`
(+중복 조사)를 **사설 워크스페이스의 실 `chat_lms.db`에 돌려** 각 테이블이 의도한 유일성을 얼마나 위반 중인지 측정한다.
이 데이터 없이 자연키를 못 박으면 #4가 실DB에서 무력화될 수 있다. → 이 단계는 **교사 측 사설 DB에서 실행**해야 한다
(이 공개 dev 레포에선 데이터가 없음).

---

## 3. Rung #4 — 멱등성을 1급 메타 능력으로

### 접근 (3개 협응 조각, 모두 제네릭·선언적, 기존 backup/rollback 재사용)

**(a) 자연키 선언 + assert-then-dedupe**
- `WriteActionTemplate`에 선택적 `indexes: {table: [[col,...], ...]}`(선언된 UNIQUE 불변식), `WriteStep`에 선택적 `natural_key: [col,...]`.
- `validate_template`: 자연키 컬럼은 화이트리스트 컬럼이어야; 자연키 스텝은 컬럼셋이 일치하는 `indexes` 항목 필수(없으면 `NATURAL_KEY_NO_INDEX_DECLARED`).
- 엔진 사전점검 `assert_indexes(conn, template)`: `PRAGMA index_list/index_info`로 **정확한 순서의 컬럼셋** UNIQUE 인덱스 존재 확인.
  없으면 **쓰기 전에 롤백** + `code 2 {MISSING_UNIQUE_INDEX, table, columns, remediation}`. ← "무성 중복 거부" 보증.
- **[QA 수정] id 캡처 멱등 스텝은 `op:'ensure'`(INSERT OR IGNORE + SELECT-back) 강제.** `lastrowid`를 바인딩하는
  `insert`+natural_key 조합은 **검증 에러로 금지**(차단 #1).

**(b) 제네릭 스키마 불변식(인덱스) 메커니즘 — `write-action index` 동사**
- 진실원천 = 로드된 모든 템플릿(repo+profile)의 `indexes` 합집합.
- `index --check`(기본, read-only): 각 (table,cols)를 `PRESENT / MISSING / TABLE_ABSENT`로 보고. **[QA] 충돌 중복 행그룹도 열거.**
- `index --apply`: 기존 backup+`BEGIN IMMEDIATE`+commit/rollback 안에서 `CREATE UNIQUE INDEX IF NOT EXISTS ux_<table>_<cols>` 실행.
  식별자는 `_valid_identifier` 검증, 인덱스명 엔진 생성(임의 SQL 없음). 기존 중복 위반 시 `INDEX_BUILD_CONFLICT`(롤백, 백업 보존).
- **[QA + 소유자결정 2026-06-27] 중복 정리 = 리포트 전용(read-only), 자동 삭제 없음.** `index --check`가 충돌 중복
  행그룹을 **목록으로만 열거**(어느 줄이 중복인지, 몇 건인지). 교사가 목록을 보고 직접/승인 정리한 뒤 `index --apply`.
  자동 `dedupe` 쓰기 동사는 **연기**(나중에 필요하면 PHASE 0 실측 중복 패턴을 보고 규칙 설계 + 별도 승인). 코드가 실 학생
  데이터를 자동 삭제하지 않는다. **인덱스명 충돌 시 해시 접미사 폴백은 초기 설계에 포함.**
- `doctor_v3`에 비-치명 점검: 선언됐으나 없는 인덱스를 `repair_action='write-action index --apply'`(`safe_to_auto_repair=False`)로 노출.

**(c) record-class / record-test-scores를 멱등 경로로**
- `record-class.json`: `session_kind`를 columns/param(default `main`)/set에 추가 → `insert_session`을 `op:'ensure'`로,
  `indexes.sessions=[[class_id,session_date,session_kind]]`. 재실행 시 sessions no-op + stub UPDATE(기존 동작), 절대 중복 없음.
- `record-test-scores.json`: `indexes.tests=[[name]]`로 `ensure_test` dedupe를 자산화. test_results 재기록 멱등 여부는 **§7 결정 필요**.

### 핵심 테스트 (예외/경계 중심)
- 자연키 선언 but 인덱스 미선언 → `NATURAL_KEY_NO_INDEX_DECLARED`(컴파일, DB 미접속).
- **[차단 회귀] 재실행 시 `session_id`가 기존 행 id로 재바인딩 + `update_attendance`가 올바른 행 적중**(ensure SELECT-back).
- 인덱스 없는 DB에 apply → `MISSING_UNIQUE_INDEX`, 행수 불변, db_dump 바이트 동일, 백업 존재.
- **[차단] 이미 중복 행 있는 테이블에 `index --apply` → `INDEX_BUILD_CONFLICT`, 롤백, 백업 보존, 충돌 행그룹 명시.**
- 컬럼 순서 틀린 UNIQUE = MISSING 취급, 부분/표현식 인덱스(origin≠'c') 무시.
- 인덱스명 충돌 → 해시 접미사 폴백.
- 하위호환 골든: `indexes`/`natural_key` 없는 템플릿은 컴파일 SQL 바이트 동일.
- fanout: 로스터 바뀐 같은 날 재실행 시 제거된 학생 stub 처리.
- 예외: SQLITE_BUSY/디스크풀 백업 실패/손상 ledger/트랜잭션 중단.

### 성공 / 실패 기준
- ✅ 자연키 선언 가능 + 백업 인덱스 부재 시 엔진이 적용을 **거부**(exit 2, 롤백) — **절대 무성 중복 안 함**.
- ✅ `index --apply`가 멱등하게 UNIQUE 생성, 트리 밖 DB에 추가적·가역안전; `--check`는 read-only.
- ✅ 인덱스 있으면 같은 class+date record-class 재실행 = sessions no-op.
- ❌ 자연키 선언됐는데 UNIQUE 부재 시 중복 행 삽입(무성) — 하드 실패.
- ❌ `CREATE TABLE`/비가역 스키마 변형을 src에 도입.
- ❌ 템플릿 문자열이 `_valid_identifier` 없이 raw 식별자로 SQL 도달.

---

## 4. Rung #5 — SessionStart로 라우트/명령 확실 전달

### 문제(검증됨)
`route_packs_context`(route_packs.py:120-138)는 `bucket=='always_inject'`에만 풀 카드 방출. record_class 등 7개
trigger 팩 + 프로파일 trigger 팩은 명령 없는 `listed` 항목으로 축소. 진짜 카드는 죽은 user-prompt-submit 분기에서만 붙음.
→ 세션 시작 시 에이전트는 라우트 *이름*만 보고 *실행법*은 못 봄 → ad-hoc SQL/HTML 폴백. `bootstrap.ps1:461-463`이 가중.

### 크기 제약(실측)
현재 SessionStart 페이로드 10,120B / 상한 11,000B → 여유 880B. 모든 팩 풀카드화=+~4,300B(초과). →
컴팩트 "command_index" 형태 + 섹션 바이트 예산 + 랭킹/절단 + 소폭 상한 인상 필요.

### 설계
**(a) command_index**: route_packs 섹션에 신규 키. bucket∈{trigger, always_inject} 팩마다 컴팩트
`{route_id, summary, first_command, then_command, must_not, source}`(fallback/time_budget 생략).
**랭킹: 프로파일 팩 우선**(새로 결정화한 워크플로가 핵심) → repo, 각 그룹 pack_id 정렬(결정적). 섹션 예산 초과 시
per-entry로 `must_not` 먼저 강등 후 항목 드랍 — **단 [QA] 쓰기형 팩(record_class 등)의 `must_not`은 비-droppable**.
드랍된 항목도 `listed`에 남아 무성 소실 없음 + 복구 힌트(`agent-tools route list`).
- always_inject `cards`는 **기존과 정확히 동일**(무회귀). command_index는 추가물.
- **[QA] 전역 상한 인상 최소화**: 가능하면 then_command까지 컴팩트, 인상 시 `APPLIED_REDUCTIONS` 기록 + 섹션상한 합과 이벤트상한 관계 테스트.

**(b) `bootstrap.ps1:461-463` 진실로 교정**: "UserPromptSubmit이 주입함" 제거 → "command_index가 SessionStart에 주입됨;
스키마검사/스캐폴딩/rg/HTML 전에 매칭 라우트의 first_command 실행; `agent-tools prompt-check ... --profile-root` 를
라이브 확인/폴백으로 **권장**"(유일 작동 게이트 재활성화). "prompt-check 수동 재실행 금지" 삭제.

**(c) registered_events 라이브니스 [QA: 모양 변경 대신 추가]**: `registered_events`(string[]) 유지 + 형제 키
`event_liveness:[{event, fires_at_runtime}]` + `liveness_note` 추가. `LIVE_HOOK_EVENTS=frozenset({'SessionStart'})`로 구동.

**(d) 프로파일 라우트 전달**: 이미 배선됨(build_host_context가 profile-wins 병합). command_index가 동일 병합 리스트를
순회·프로파일 우선 → 새 결정화 라우트가 다음 세션에 명령과 함께 노출. **회귀 테스트로 폐루프 단언.**

### 핵심 테스트
- 골든 SessionStart 페이로드(프로파일 저작 라우트 포함)가 command_index에 first_command와 함께 등장.
- **실 repo 팩 기준** 섹션+베이스 합이 (인상된) 상한 이하 — 합성 픽스처 아님(드리프트 방지).
- record_class.first_command 있으면 record_class.must_not 반드시 동반(비-droppable).
- 프로파일+동일id repo 팩 → profile-wins + 전순서(profile=0/repo=1, pack_id asc) 절단 하 결정성.
- 드랍 항목이 `listed`에 복구 힌트와 함께 잔존.
- always_inject 카드 무회귀.

### 성공 / 실패 기준
- ✅ 어떤 운영 라우트도(프로파일 포함) 매 세션 SessionStart만 읽어 first/then + must_not 발견·실행 가능.
- ✅ 오도 문구 제거, 죽은 훅 의존 0, prompt-check 폴백 재활성.
- ❌ must_not(쓰기형)이 명령만 남기고 드랍됨(거짓 자신감 실행).
- ❌ registered_events 모양 파괴로 에이전트 소비 깨짐.

---

## 5. Rung #6 — 제네릭 OS 스케줄러 primitive

### 접근
`schedule` 동사(신규 `schedule.py` 순수로직 + `schedule_handlers.py` I/O + `schedule_backend.py` 백엔드 seam).
**스케줄되는 건 자유 셸 문자열이 아니라 기존 승인 primitive 참조** — `kind∈{shortcut, write-action, outbound}` + 바인딩 인자.
생성 작업은 **항상 워크스페이스 래퍼 `chat-lms-cli.ps1`**를 고정 verb 라인으로 호출 → 임의 SQL/셸 밀반입 불가.

**신뢰 게이트**: `register`가 특권 단계. 첫 호출 `NEEDS_APPROVAL`(exit 3), `plan_id=schedule:<job_id>`(job_id=kind+인자+트리거
+**[QA] 프로파일루트** 콘텐츠 해시). 교사가 실 터미널에서 `approval approve --actor <human>`(AGENT 자가승인 거부 재사용).
재등록=동일 job_id 업데이트(중복 없음, 멱등).

**[QA 차단 #4] standing 승인**: 반복 잡은 소비 안 되는 상시 승인(`schedule-exec:<job_id>`), job_id 변경/revoke 시 무효.
`approvals.py`에 `approval_is_standing`/`revoke_standing` 신설.

**실행 자체 = primitive 자신의 안전 모드.** **v1 기본 = dry-run**(예: `outbound ... sync` `--execute` 없이 → PASS+execute_required,
외부 쓰기 불가). execute 승격은 **별도 `--unattended-execute`** + 더 큰 승인 스코프, **그리고 [QA 차단 #6] 바인딩 #4 템플릿의
UNIQUE 인덱스 PRESENT 검증 통과 시에만 허용.**

**[QA 차단 #5] 프로파일 루트 명시 핀**: 생성 작업 액션에 `CHAT_LMS_AGENT_PROFILE_ROOT`를 명시 설정/`--profile-root` 전달.
위치 추론 금지. 로그오프 실행 여부 **실측 후 정직 문서화**(과거 "죽은 능력 광고" 교훈).

**무인 실패**: 바인딩 명령이 exit 3/5/6 → 안전 no-op, 잡별 JSONL run-log에 `outcome:needs_human` 기록(append-only, bounded,
never-raises). `schedule status/runs`로 교사가 "이 잡이 당신을 기다림" 확인.

**비수업일**: `--skip-when` read-only 프로브(기존 `_active_on`/`class_schedule_exceptions` 재사용) → `skipped_no_class`.

**정리**: `remove --id/--all`, `prune`(ledger↔실작업 조정). 작업명 `ChatLMS_<profile-slug>_<job_id12>` under `\ChatLMSAgent\` →
프로파일 네임스페이스 격리(교사간 교차 삭제 불가).

### 핵심 테스트 (전부 FakeBackend로 실 Task Scheduler 무접촉)
- `plan` dry-run이 올바른 래퍼 명령+작업명, 백엔드 호출 0/ledger 미기록.
- register 멱등(동일 job_id 업데이트), 미승인 시 exit 3 무작업, 자가승인/repo-root 거부.
- **[차단] PowerShell 인용**: `-File`+argv 배열, 공백 포함 래퍼 경로/인자, **적대 입력**(따옴표·세미콜론·`&`·백틱·`%VAR%`·유니코드) 각 1토큰 유지·무확장.
- 기본 잡=primitive dry-run 형태(`--execute` 부재), `--unattended-execute`+승인 시에만 execute.
- 무인 게이트 적중 → `needs_human` 기록 + 외부 쓰기 0.
- skip-when 비수업일 단락.
- **[차단] standing 승인**: N회 생존, job_id 변경 시 재승인 강제, AGENT 자가승인 불가.
- ledger↔실작업 드리프트 조정, 프로파일 네임스페이스 격리.
- run-log PII 레닥션(학생명/점수 입력 → JSONL에서 마스킹).
- **[교차] `--unattended-execute` 잡은 #4 인덱스 PRESENT 아니면 거부.**
- 실 백엔드 생성 XML/argv 정형성 스냅샷(적대 인자).

### 성공 / 실패 기준
- ✅ 교사 1회 승인 후, 저작 결정적 명령이 (검증된 한도 내) 세션 없이 타이머/달력으로 실행, 멱등·격리·로그.
- ✅ execute 잡은 #4 멱등성 검증 통과 시에만, 기본은 dry-run.
- ❌ 무인 실행이 승인 없이 외부 쓰기 / 미멱등 템플릿 무인 반복 / 다른 프로파일 DB 기록 / 인자 토큰 인젝션.

---

## 6. 교차-단 불변식 (QA 통합)

1. execute 스케줄 잡 ⟹ 바인딩 #4 템플릿 멱등(UNIQUE PRESENT) 필수.
2. #5 command_index는 #4가 적용된(멱등) 템플릿을 가리켜야 함 — 안 그러면 미안전 record_class를 더 쉽게 실행시킴(순서 #4→#5 이유).
3. 백업 보존 정책: 무인 반복 실행이 `run_write_action`/`index --apply`로 백업 양산 → **보존/정리 정책 필수**.
4. 동시성: 무인 잡(`BEGIN IMMEDIATE`)과 라이브 세션 충돌(SQLITE_BUSY) → `busy_timeout`+retry, run-log에 `retry` outcome.

---

## 7. 소유자(교사) 결정 필요 항목

1. ~~sessions 자연키~~ → **확정: `(class_id, session_date, session_kind)`** (2026-06-27).
2. **test_results 재기록**: 멱등(자연키) vs append(현행) — **권장 멱등**(단 기존 테스트 의미 변경, 회귀 테스트 유지). *미정.*
3. ~~v1 스케줄러 execute 허용 여부~~ → **확정: dry-run-only 먼저** (2026-06-27). execute는 post-v1.
4. **#6 로그오프 실행 요구**: 필수인지(→ Task Scheduler 설정·실측), 로그온 한정 허용인지. dry-run v1에선 저위험. *미정.*

---

## 8. 실행 메모

- PHASE 0(중복 조사)는 **사설 워크스페이스 실 DB**에서 실행 — 공개 dev 레포엔 데이터 없음. 빌드는 여기서, 측정은 교사 측.
- TDD, 손댄 파일 ruff/basedpyright 클린, 예외/경계/동시성 테스트 대폭(사용자 룰: "너무 많은 테스트가 항상 낫다").
- 코딩 에이전트 ↔ 독립 QA 에이전트 분리 유지(이 설계도 그 방식으로 검증됨).
