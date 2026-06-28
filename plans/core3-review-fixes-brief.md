# 수정 브리프 — core3 PR-직전 적대 리뷰 결함 6개 (ulw-loop 입력용)

> 브랜치 `feat/meta-harness-crystallization-core3` (HEAD 6f79765) 위에서 작업. 이미 `uv run pytest` 510 green.
> 적대 리뷰(독립 QA)가 그린 테스트가 못 잡은 실제 결함 6개를 file:line + 재현으로 확정. 전부 TDD로 수정한다.

## 절대 가드레일

- **이 6개 결함만 수정.** 범위 밖 리팩터/기능 추가 금지. 막히면 멈추고 보고.
- **건드리지 말 것(미커밋 WIP)**: `scripts/bootstrap.ps1`, `src/chat_lms_agent/daily_management_outbound.py`, `src/chat_lms_agent/session_ledger.py`, `tests/test_outbound_sync.py`, `tests/test_session_ledger.py`, `tests/test_bootstrap_session_log_wiring.py`. 이 파일들은 다른 작업의 WIP다.
- TDD: 각 결함마다 **실패하는 테스트를 먼저 쓰고** 고친다. 기존 510 테스트 회귀 금지. 손댄 파일 `ruff`+`basedpyright` 클린.
- 확정 결정 불변: 자연키=(class_id,session_date,session_kind); 스케줄러 v1 dry-run 전용; 중복 리포트 전용; 임의 SQL/CREATE TABLE 금지.

## 결함 6개

### F1 [high] 쓰기/전송형 팩의 must_not 가드가 command_index에서 탈락
- 위치: `src/chat_lms_agent/route_packs.py:250-260` `_must_not_is_non_droppable`.
- 문제: non-droppable 판정이 하드코딩 `{record_class, record_test_scores}` 또는 `"write-action apply"` 문자열에만 True. 그래서 `kakao_channel`(must_not "승인 없이 카톡 전송 금지"), `gws_upload`(must_not "gmail 전송은 승인 필수")가 droppable로 분류돼 기본 예산에서 must_not째로 탈락. 재현: 기본예산 2800에서 dropped={gws_schedule, gws_upload, kakao_channel}, 두 승인 가드가 렌더 결과 어디에도 없음.
- 수정: **non-droppable을 "must_not이 비어있지 않으면 non-droppable"로** 일반화(가드레일은 명령과 항상 동행). 하드코딩 id/문자열 제거. 그러면 가드 있는 엔트리는 must_not 스트립도 안 되고, 통째로만 listed로 빠짐(분리된 반쪽 가드 불가).
- 테스트: 기본예산에서 `kakao_channel`·`gws_upload`의 must_not이 command_index 엔트리에 살아있음을 단언. 새 승인-게이트 라우트 추가 시 자동 보호되는지(비어있지 않은 must_not) 단언.

### F2 [medium] ensure의 set이 자연키 컬럼 누락해도 검증 통과 → NULL distinct로 무성 중복
- 위치: `src/chat_lms_agent/write_actions.py:159-204` `_step_errors`.
- 문제: natural_key 컬럼이 step.set(INSERT 투영)에 포함되는지 검사 안 함. 누락 시 INSERT OR IGNORE가 키 컬럼 NULL로 삽입 → SQLite UNIQUE는 NULL을 distinct 취급 → 매 재실행마다 새 행(무성 중복). 재현: natural_key=(class_id,session_date,session_kind)인데 set에 session_kind 없으면 `validate_template==[]`.
- 수정: step.natural_key가 있으면 **모든 자연키 컬럼이 step.set의 키로 존재**해야 함. 없으면 `NATURAL_KEY_NOT_IN_INSERT_SET` 에러.
- 테스트: 자연키 컬럼이 set에 빠진 템플릿 → 검증 에러; 정상 템플릿(record-class) → 무회귀.

### F3 [medium] ensure의 match≠자연키여도 통과 → SELECT-back 엉뚱한 행/오류
- 위치: 동 `_step_errors`. ensure SELECT-back은 `step.match`로 컴파일(`write_actions.py:342`), match≠natural_key 검사 없음.
- 문제: (a) match가 자연키의 진부분집합이면 SELECT가 임의 행 반환 → 잘못된 id 캡처 → 후속 update_stub이 엉뚱한 행 갱신. (b) match가 상위집합/다른 바인딩이면 SELECT 0행 → LookupMiss → 멱등이어야 할 op이 롤백.
- 수정: step.natural_key가 있으면 **set(step.match)==set(step.natural_key)** 요구(아니면 `ENSURE_MATCH_NOT_NATURAL_KEY`). (선택: 공유 컬럼의 match/set 바인딩 토큰 동일성도 검사.)
- 테스트: match가 자연키 부분집합/상위집합인 템플릿 → 검증 에러; record-class/record-test-scores(match==natural_key) → 무회귀.

### F4 [medium] schedule remove에 네임스페이스/승인 게이트 없음 → 교차 프로파일 삭제(잠재)
- 위치: `src/chat_lms_agent/schedule_handlers.py:141` `_remove`. raw `--name`을 검증 없이 `backend.remove_job`에 전달, profile 안 받음, 승인 없음. register는 승인 게이트(84-99)인데 remove는 무방비(비대칭). job_name은 `ChatLMS_<profile_slug>_<digest>`(schedule.py:69).
- 수정: `_remove`에 profile을 전달하고, `--name`이 **현재 프로파일 네임스페이스 접두사 `ChatLMS_{_profile_slug(profile.root)}_`로 시작**하지 않으면 거부(UNSAFE/에러코드). (참고: `shortcut_handlers._remove`는 이미 profile 받아 경로검증함 — 그 패턴 미러.) remove도 register와 같은 승인 흐름으로 게이트하는 것이 이상적이나, 최소한 네임스페이스 접두사 검증은 필수.
- 테스트: 다른 프로파일 접두사 이름 remove → 거부; 자기 프로파일 잡 remove → 통과; 접두사 없는/경로탈출 이름 → 거부.

### F5 [low] run-log PII 정규식이 4자리+ 숫자(전화/학생ID) 누출
- 위치: `src/chat_lms_agent/schedule.py:24` `_NUMBER_RE = r"\b\d{1,3}(?:\.\d+)?\b"`. 1~3자리만 마스킹 → 전화(01098765432)·학생ID(12345)·점수(9999) 통과.
- 수정: 다자리 숫자도 마스킹. 예 `re.compile(r"\d{2,}")` 또는 상한 제거(`\d{1,}`). 현재 유일 호출부는 하드코딩 문자열이라 실누출은 잠재지만, PII 안전장치 함수이므로 올바르게.
- 테스트: 4자리+ ID/전화형 문자열이 run-log에서 마스킹됨을 단언.

### F6 [medium] 실 repo 팩이 기본예산에서 무성 탈락 + section/event 상한 런타임 미강제
- 위치: `src/chat_lms_agent/route_packs.py:27`(DEFAULT_COMMAND_INDEX_BUDGET=2800), `:123-145`(cards/listed 무예산), `src/chat_lms_agent/context.py`(section/event 상한이 빈 프로파일 테스트로만 검증).
- 문제: (a) 실 7개 trigger 팩(full 4159B)이 2800 예산에서 3개 무성 탈락, 실파일 기준 dropped==empty 테스트 없음. (b) always_inject `cards`/`listed` 리스트가 무예산 → 프로파일이 always_inject 팩 몇 개 추가하면 route_packs 섹션 상한(4500)·이벤트 상한(13800)을 마커도 복구힌트도 없이 돌파.
- 수정:
  - (a) **모든 shipped trigger 팩이 first_command과 함께 command_index에 남도록** 한다. write 팩(must_not 있는)은 first+then+must_not 보존이 우선이므로 명령을 깎지 말고, 대신 `DEFAULT_COMMAND_INDEX_BUDGET`을 실 팩이 들어갈 만큼 상향하고, 그에 맞춰 `CONTEXT_SECTION_BYTE_CEILINGS['route_packs']`·`CONTEXT_EVENT_BYTE_CEILING`을 **실측에 근거해 최소로** 올린다(상향분은 APPLIED_REDUCTIONS/주석에 근거 기록). non-write 팩은 then_command 생략 등 엔트리 축소를 허용해 상향폭을 줄여도 됨(단 first_command·write팩 must_not은 보존).
  - (b) `cards`/`listed`도 command_index처럼 **섹션 바이트 예산으로 제한 + 초과분은 마커/복구힌트**를 emit(메모리 섹션 budgeting 패턴 미러). 런타임에 section/event 상한이 실제로 지켜지게.
- 테스트: 실 repo 팩 로드 → 기본예산 command_index에서 **dropped==empty** 단언(미래 팩 추가/예산 회귀 시 실패하게). always_inject 팩 다수인 프로파일 → route_packs 섹션·이벤트 상한 준수 + 마커 존재 stress 테스트.

## 완료 기준

- 6개 결함 각각 실패테스트→수정→그린. 전체 `uv run pytest` green(기존 510 무회귀 + 신규). 손댄 파일 ruff/basedpyright 클린.
- F1: kakao_channel·gws_upload must_not이 기본예산 command_index에 생존.
- F6: 실 repo 팩 dropped==empty; cards/listed 포함 section·event 상한 런타임 강제.
- WIP 6파일 무수정.
- 한 결함 끝낼 때마다 보고. 막히면 정지.
