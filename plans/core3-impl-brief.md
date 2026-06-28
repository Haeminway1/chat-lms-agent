# 구현 브리프 — 메타 하네스 코어3단 (ulw-loop / 자율 코딩 루프 입력용)

> 이 문서는 자율 구현 루프(lazycodex ulw-loop 등)에 그대로 먹이는 **자기완결형 작업 지시서**다.
> 전체 설계: `plans/meta-harness-crystallization-core3-plan.md` (먼저 읽을 것). 이 브리프는 그 설계의 v1 실행 슬라이스다.
> 레포: 공개 dev 레포 `<repo-root>` (Python `src/chat_lms_agent`, PowerShell `scripts/bootstrap.ps1`).

## 미션 (한 줄)

chat_lms 메타 하네스의 "결정화 루프" 코어 3단을 복구한다. 제네릭 메타 능력만 만든다 — `ensure-today` 같은 도메인
워크플로는 손코딩하지 않는다.

## 절대 가드레일 (이탈 금지 — 헤맴 방지)

- **설계 문서 범위 밖으로 나가지 말 것.** 새 기능·리팩터·"개선"을 임의 추가 금지. 막히면 멈추고 보고.
- **실 학생 데이터 자동 삭제·수정 금지.** 중복 정리는 **리포트(목록)만**. `dedupe` 쓰기 동사 만들지 말 것.
- **`CREATE TABLE`/스키마 파괴 금지.** 프로덕션 스키마는 트리 밖. 허용된 유일한 스키마 변경은 `CREATE UNIQUE INDEX IF NOT EXISTS`뿐.
- **임의 SQL 금지.** 모든 식별자는 기존 `_valid_identifier` 통과. 선언적 DSL만.
- **기존 동작 회귀 금지.** `indexes`/`natural_key` 없는 템플릿은 바이트 단위로 동일하게 동작해야 함.
- TDD 필수. 손댄 파일 `ruff` + `basedpyright` 클린. 테스트는 많을수록 좋다(예외/경계/동시성 포함).
- 각 단계 끝에 **독립 검증(QA) 패스**: 구현 에이전트와 분리된 에이전트가 테스트·가드레일·회귀를 검증.

## 확정 결정 (변경 금지)

1. sessions 자연키 = `(class_id, session_date, session_kind)`. `record-class.json`에 `session_kind` 컬럼/파라미터(default `'main'`)/insert set 추가.
2. 스케줄러 v1 = **dry-run 전용**. `--unattended-execute`/standing 승인/로그오프 실행은 만들지 말 것(post-v1).
3. 기존 중복 = **리포트 전용**. 코드 자동 삭제 없음.
4. test_results 재기록 = **멱등(덮어쓰기)**. 기존 append-동작 테스트는 회귀 테스트로 유지하며 의미 변경 명시.

## 구현 순서 (이 순서 엄수 — 안전 의존성)

### STEP 1 — 읽기 전용 "중복 점검기" (`write-action index --check`)
- 로드된 모든 템플릿(repo+profile)의 선언 `indexes`를 모아, 사설 DB(`profile.root/data/chat_lms.db`)를 **read-only**로 열어
  각 (table, cols)를 `PRESENT / MISSING / TABLE_ABSENT`로 보고.
- 추가로 **충돌 중복 행그룹을 목록으로** 출력(어느 키가 몇 번 중복인지). **삭제·수정 절대 없음.**
- 파일: `write_action_handlers.py`(+`_index`), `write_action_parser.py`(`index` 서브파서, `--check` 기본), `write_actions.py`
  (`indexes`/`natural_key` 파싱 + `backing_index_specs` 헬퍼 + 검증 `NATURAL_KEY_NO_INDEX_DECLARED`).
- 출력: JSON `{status, db_present, indexes:[{table,columns,state}], conflicts:[{table,columns,row_groups...}]}`, read-only는 항상 exit 0(또는 DB_UNAVAILABLE exit 2).
- 테스트: PRESENT/MISSING/TABLE_ABSENT 각각, 중복 있는 픽스처에서 충돌 행그룹 열거, read-only 단언(db_dump 불변), 자연키-인덱스 미선언 검증 에러.
- **이 단계 산출물은 그대로 교사 사설 DB에서 1회 실행해 실제 중복 수를 측정하는 데 쓰인다(코딩 아님, 사용자 손 필요).**

### STEP 2 — "두 번 눌러도 안전" (#4 멱등)
- `WriteActionTemplate.indexes` + `WriteStep.natural_key` 선언 지원. 엔진 사전점검 `assert_indexes(conn, template)`:
  `PRAGMA index_list/index_info`로 정확한 순서 컬럼셋 UNIQUE 확인, 없으면 **쓰기 전 롤백 + exit 2 `MISSING_UNIQUE_INDEX`**.
- **[차단 회귀 주의] id 캡처 멱등 스텝은 `op:'ensure'`(INSERT OR IGNORE + SELECT-back) 강제.** `insert`를 OR IGNORE로
  바꾸지 말 것(`lastrowid`가 재실행 시 기존 행 id를 못 줌). `record-class.insert_session`을 `op:'ensure'`(match=class_id+session_date+session_kind)로 전환.
- `write-action index --apply`: 기존 backup+`BEGIN IMMEDIATE`+commit/rollback 안에서 `CREATE UNIQUE INDEX IF NOT EXISTS`.
  기존 중복으로 실패 시 `INDEX_BUILD_CONFLICT`(롤백, 백업 보존). 인덱스명 충돌 시 해시 접미사 폴백.
- `record-class.json`/`record-test-scores.json`에 `indexes` 선언 + session_kind/멱등 반영.
- 테스트(필수, 예외 포함): 재실행 시 session_id가 **기존 행 id로 재바인딩** + update_attendance 올바른 행 적중; 인덱스
  부재 시 MISSING_UNIQUE_INDEX·행수불변·백업존재; 중복행 있을 때 INDEX_BUILD_CONFLICT·롤백; 컬럼순서 틀린 UNIQUE=MISSING;
  부분/표현식 인덱스 무시; 하위호환 골든(SQL 바이트 동일); fanout 로스터 변경; SQLITE_BUSY/디스크풀/손상 ledger.

### STEP 3 — "버튼을 조교 눈앞에" (#5 라우트 전달)
- `route_packs_context`에 `command_index` 추가: bucket∈{trigger, always_inject} 팩마다 컴팩트
  `{route_id, summary, first_command, then_command, must_not, source}`. 프로파일 팩 우선 정렬. 섹션 바이트 예산 + 절단 마커.
  **쓰기형 팩(record_class 등) must_not은 비-droppable.** always_inject `cards`는 기존과 정확히 동일(무회귀).
- 컨텍스트 상한: 먼저 압축으로 인상 0 시도, 불가피하면 최소 인상 + `APPLIED_REDUCTIONS` 기록.
- `bootstrap.ps1:461-463` 오도 제거: "UserPromptSubmit이 주입" 삭제, prompt-check 폴백 **권장**으로 전환.
- `registered_events`는 모양 변경 말고 형제 키 `event_liveness:[{event,fires_at_runtime}]` + `liveness_note` 추가(`LIVE_HOOK_EVENTS={'SessionStart'}`).
- 테스트: 프로파일 저작 라우트가 command_index에 first_command와 등장(폐루프); 실 repo 팩 기준 바이트 예산 단언; record_class.must_not 비-droppable; profile-wins 결정성; 드랍 항목이 listed에 복구힌트와 잔존; always_inject 무회귀.

### STEP 4 — "미리보기 알람" (#6 dry-run 스케줄러)
- `schedule.py`(순수)+`schedule_handlers.py`(I/O)+`schedule_backend.py`(`TaskSchedulerBackend` Protocol, FakeBackend로 테스트).
  `schedule_parser.py`, `command_parser.py`/`commands.py` 등록(`shortcut` 패턴 미러).
- 스케줄 대상 allowlist = `{shortcut, write-action(dry-run), outbound(sync, --execute 없이)}`. 자유 셸 문자열 금지. 항상 워크스페이스 래퍼 `chat-lms-cli.ps1` 경유.
- `register` 교사 승인 게이트(작업 생성 1회 승인; AGENT 자가승인 거부 재사용). 재등록=job_id(콘텐츠 해시, **프로파일 루트 포함**) 업데이트(중복 없음).
- **프로파일 루트 명시 핀**(작업 액션에 env/`--profile-root`), 위치 추론 금지. **외부 쓰기 경로 0**(dry-run만).
- PowerShell argv는 `-File`+argv 배열, 단일 인용 헬퍼, 적대 입력 테스트(공백·따옴표·세미콜론·`&`·백틱·`%VAR%`·유니코드).
- run-log append-only/bounded/never-raises. `list/status/runs/remove/run-now/plan`. 프로파일 네임스페이스 격리.
- 테스트: 전부 FakeBackend; plan dry-run 부작용 0; register 멱등·미승인 exit3·자가승인/repo-root 거부; 인용 적대입력;
  기본 잡=primitive dry-run 형태(`--execute` 부재); 게이트 적중 시 needs_human 기록+외부쓰기0; skip-when 비수업일; 드리프트 조정; run-log PII 레닥션; 실 백엔드 생성 argv 스냅샷.

## 완료(성공) 기준 — 각 STEP

- STEP1: `index --check`가 read-only로 중복을 목록 보고; 삭제 0; 테스트 그린.
- STEP2: 같은 class+date record-class 재실행 = sessions no-op(중복 0); 인덱스 부재 시 적용 거부(롤백); 하위호환 무회귀; 테스트 그린.
- STEP3: 매 세션 SessionStart만 읽어 운영 라우트 first_command + must_not 발견 가능(프로파일 라우트 포함); 오도 문구 제거; 무회귀.
- STEP4: 교사 승인 후 dry-run 잡이 타이머로 미리보기 실행(외부 쓰기 0), 멱등·격리·로그; 모든 테스트 FakeBackend로 그린.
- 전부: 전체 스위트 그린, 손댄 파일 ruff/basedpyright 클린, 독립 QA 패스.

## 실패 기준 (하나라도 해당 시 멈추고 보고)

- 자연키 선언했는데 UNIQUE 부재 시 중복 행 무성 삽입.
- 재실행 시 session_id가 엉뚱한 값에 바인딩(lastrowid 오류 재발).
- 실 학생 데이터 자동 삭제/수정; `CREATE TABLE`/스키마 파괴; 임의 SQL 식별자 미검증.
- `indexes`/`natural_key` 없는 템플릿 동작 변화(회귀).
- 스케줄러가 외부 쓰기 수행(dry-run v1 위반) 또는 프로파일 루트 추론으로 다른 프로파일 DB 접근.
- 컨텍스트에서 쓰기형 must_not이 명령만 남기고 드랍.

## 운영 메모

- PHASE 0(중복 실측)은 STEP1 산출물을 **사설 워크스페이스 실 DB에서 1회 실행** — 공개 레포엔 데이터 없음.
- ulw-loop은 stdin redirect 필요(메모리: routing-and-lesson-panel-shipped).
- 한 STEP 끝낼 때마다 "됐고/다음" 보고. 막히면 임의 진행 말고 정지.
