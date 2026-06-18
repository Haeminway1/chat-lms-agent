# Chat LMS Agent

> 🌐 **언어:** **한국어** · [English](README.en.md)

한국인 선생님 한 명을 위한 **로컬 LMS(학습 관리) 에이전트**입니다. 선생님은 AI
에이전트와 **자연스러운 한국어 대화**로만 일하고, 이 저장소는 그 대화를 안전하고
반복 가능하게 만들어 주는 **하네스(harness)** — 즉 정해진 명령 표면, 안전 게이트,
기록 원장(ledger), 메모리 — 를 담당합니다.

실제 AI는 **Codex Desktop**이 돌립니다. 이 저장소는 LLM 루프를 직접 돌리지
않으며, Codex의 세션 수명주기 훅(lifecycle hook)에 붙어 동작합니다. 모든 위험한
작업은 **사람이 그 자리에서(human-present)** 직접 승인해야 하고, 실제 학습 데이터는
전부 이 저장소 **바깥의 비공개 작업공간**에만 저장됩니다.

- 제품 의도와 단계: **[PRD.md](PRD.md)**
- 코드 구조 지도 (코드 탐색은 여기부터): **[docs/architecture.md](docs/architecture.md)**
- 계획 이력과 상태: **[plans/STATUS.md](plans/STATUS.md)**
- 선생님용 설정·매일 기입·ClassCard·세션 로그 검토: **[docs/teacher-runbook.md](docs/teacher-runbook.md)**
- Codex 플러그인 / 마켓플레이스 등록 (수동 설치): **[codex-plugin/README.md](codex-plugin/README.md)**

---

## 한눈에 보는 구조

```text
Codex Desktop (AI 에이전트 런타임 — 두뇌, 채팅 UI, 도구 실행)
   │  세션 수명주기 훅 (SessionStart ~ Stop)
   ▼
chat-lms CLI (이 저장소, src/chat_lms_agent/)
   │  허가된 명령으로만 읽고/쓴다
   ▼
비공개 프로필 작업공간 (<LOCALAPPDATA>/…, 절대 이 저장소 안이 아님)
   └─ .chat-lms-state/  승인 기록, 메모리, 저널, 목표, 블록, 텔레메트리
```

**두 개의 세계 (엄격한 경계)**

| 공개 저장소 (이 체크아웃) | 비공개 프로필 작업공간 |
| --- | --- |
| 코드, 테스트, 계획, 문서, 기본 라우트 팩, 모델 카탈로그 | 학습 데이터, DB, 리포트, 백업, 메모리, 모든 원장 |
| 공개해도 안전 — 프라이버시 테스트가 검사함 | `scripts/bootstrap.ps1`이 생성 · 세션마다 안전한 설정을 자동 동기화 |

실제 학습 데이터는 공개 저장소 안에 절대 들어오지 않으며, 모델로 나가는 모든
텍스트는 비밀값·경로 마스킹과 학습자 개인정보 가명화를 거칩니다.

---

## 주요 기능

- **세션 수명주기 훅** — `SessionStart`부터 `Stop`까지 모든 세션 이벤트를
  처리합니다. 실행 전 안전 게이트, 그리고 기록이 끝나지 않으면 세션 종료를
  막으면서 복사-붙여넣기용 한국어 보정 명령을 띄우는 지식 마감 게이트를
  포함합니다.

- **사람이 직접 하는 단발성 승인** — 실제 터미널에서 승인 id를 손으로 입력해야
  합니다. 에이전트가 스스로를 승인하는 것은 구조적으로 불가능합니다.

- **예산 기반 결정적 컨텍스트 주입** — 로컬 top-K 메모리 회상(한국어 + 영어,
  임베딩 없음)으로 이벤트별로 필요한 만큼만 컨텍스트를 넣습니다.

- **게이트가 걸린 런타임 확장성** — 에이전트 도구, 보조 패널 블록, 프롬프트
  라우트 팩은 모두 초안 → 증거 → 선생님 승인 파이프라인을 거쳐서만 늘어납니다.
  프로덕션 화면에는 검토되지 않은 초안이 절대 올라가지 않습니다.

- **결정적 DB 기입(쓰기) 엔진** — 범용 `write-action` 엔진이 데이터로 정의된
  템플릿(`write-action-v1`)을 고정된 파라미터 SQL로 컴파일합니다. 임의 SQL도,
  조인도 없습니다. 한 번의 백업된 원자적 트랜잭션으로 실행하고, ID·건수만 남기는
  감사 행을 기록하며, `apply`는 **선생님이 승인한 등록**에만 허용됩니다. 수업
  하루치(출석·숙제·진도·점수) 기록이 손으로 쓰는 SQL 대신 명령 하나가 됩니다.
  새 쓰기 기능은 코드가 아니라 데이터 템플릿으로 추가합니다.

- **자동 세션 트랜스크립트 로깅** — 모든 Codex 세션(프롬프트, 에이전트의 설명
  메시지와 도구 호출 순서, 각 도구 호출의 인자·출력, 토큰 사용량, 턴별
  모델·승인 상태)이 Codex 롤아웃에서 비공개 작업공간의 영구 검토 로그로
  수집됩니다. 두 개의 네이티브 트리거(Codex `notify` 프로그램 + 분리된
  SessionStart 따라잡기)가 비동기로 돌아 라이브 세션을 절대 느리게 하지 않으며,
  디스크에는 비밀값·경로가 제거되고 학습자 이름이 가명화된 채 저장됩니다.

- **모델·호스트 독립성** — 역할 → 계열 → 구체 모델 카탈로그와 단일 호스트
  어댑터 모듈을 두어, 가짜 호스트(fake-host) 엔드투엔드 테스트로 검증합니다.
  (현재 지원되는 런타임은 Codex Desktop 하나뿐입니다.)

- **프라이버시 강제** — 저장소 전체 프라이버시 스캔, 비밀값·경로 마스킹, 모델로
  나가는 모든 텍스트에 대한 2단계 학습자 개인정보 가명화.

> `src/chat_lms_agent/` 아래 약 120개 모듈, 440개 이상의 격리(hermetic) 테스트,
> 런타임 의존성 0개. CI는 Windows 우선 레인(`.github/workflows/ci.yml`)으로
> 돌아갑니다.

---

## 요구 사항

- **Python 3.12 이상**
- **[uv](https://docs.astral.sh/uv/)** (의존성·가상환경 관리)
- **Codex Desktop** (AI 에이전트를 실제로 구동하는 런타임)
- **Windows** (CI·부트스트랩이 Windows 우선; PowerShell 스크립트 사용)
- (선택) ClassCard 자동화를 쓰려면 Playwright + Chromium

---

## 설치 방법

설치는 두 가지 용도로 나뉩니다. **개발용**은 이 저장소를 직접 쓰고, **실제
사용용**은 학습 데이터를 다루는 비공개 작업공간을 따로 만듭니다.

### 1) 개발용 (코드 작업)

저장소를 클론한 뒤 루트에서:

```bash
uv sync --dev
uv run pytest          # 전체 테스트 (격리됨 · 실제 프로필을 절대 건드리지 않음)
uv run ruff check      # select=ALL
uv run basedpyright    # typeCheckingMode=all
```

프로덕션 코드보다 **테스트를 먼저** 추가합니다. 문서는 계약입니다
(`tests/test_docs_contract.py`). 저장소는 항상 공개 가능한 상태를 유지해야
합니다(`tests/test_repo_privacy.py`).

### 2) 실제 사용용 (비공개 작업공간 + 격리된 Codex 환경)

실제 수업 데이터는 이 저장소가 아니라 **비공개 프로필 작업공간**에 둡니다.
저장소 루트에서 다음을 실행하면 만들거나 갱신할 수 있습니다:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -Mode User -Profile <your-name>
```

이 명령은 로컬 앱데이터(`<LOCALAPPDATA>`) 아래 프로필 루트에 다음을 생성합니다:

- `codex-workspace/` — 실제 사용 작업공간 (AGENTS.md, 훅, CLI 래퍼, 프로필 마커)
- `data/chat_lms.db` — 비공개 학습자 데이터베이스 (절대 저장소에 들어오지 않음)
- `codex-home/config.toml` — **chat-lms 플러그인만** 켜는 깨끗한 Codex 홈
  (서드파티 플러그인 없음, 에이전트 오케스트레이션 매니페스토 병합 없음,
  텔레메트리 없음)
- `codex-home/launch-teacher-codex.cmd` — 그 깨끗한 홈으로 Codex Desktop을
  띄우는 런처

이 비공개 작업공간은 실제 DB·리포트·백업·로그·비공개 메모리를 담으며, 저장소를
안전하게 공개할 수 있도록 **의도적으로 분리**되어 있습니다.

작업공간의 SessionStart 훅이 이 저장소의 안전한 런타임 설정을 세션마다 자동
동기화하므로, 선생님이 수동 명령을 기억하지 않아도 됩니다. 다만 데이터 임포트,
DB 마이그레이션, 자격증명, 외부 쓰기, 파괴적 변경은 여전히 — 실제 터미널에서
승인 id를 손으로 입력하는 — **명시적 승인**이 필요합니다.

### 3) 첫 실행 (Codex가 요구하는 보안 2단계 — 자동화 불가)

1. 실행 중인 **Codex Desktop을 완전히 종료**합니다(모든 창을 닫고 트레이에서도
   종료). 단일 인스턴스라서, 켜져 있으면 새 홈을 무시합니다.
2. `launch-teacher-codex.cmd`를 더블클릭합니다("Codex (Teacher)"로 고정 추천).
3. 그 세션에서 `codex login`을 한 번 실행합니다(인증은 홈 단위).
4. `codex-workspace` 폴더를 열고, 1회성 **chat-lms 훅 신뢰(trust)** 프롬프트를
   승인합니다.

### 4) 기입 write-action 등록 (신뢰 경계, 1회)

수업 기록은 선생님이 승인한 등록에만 허용됩니다. (`<cli>`는 작업공간의
`scripts/chat-lms-cli.ps1` 래퍼입니다.)

```powershell
# 1) 등록 요청 (승인 id를 출력)
<cli> write-action register --id record-class --profile-root <profile-root> --json
# 2) 실제 터미널에서 승인 (승인 id를 손으로 입력)
<cli> approval approve --id <approval-id> --actor <your-name>
```

점수도 기록한다면 `record-test-scores`도 같은 방식으로 한 번 등록합니다. 이후
매일의 기록은 자동으로 돌아갑니다.

> 격리 설정에 대한 더 자세한 단계별 안내(다운로드 → 격리 환경 → 첫 기입)는
> **[docs/teacher-runbook.md](docs/teacher-runbook.md)** 에 있습니다.

---

## 사용 방법

일상적으로는 **선생님이 한국어로 에이전트에게 말하면** 됩니다. 아래 명령들은
수동·검증용입니다.

### 수업 하루치 기입

그냥 한국어로 말합니다. 예:

> EBSS 전원 출석, 숙제 100, 진도 unit 1 weekly test, 점수 원우 13/15 하린 12/15

에이전트는 손으로 쓰는 SQL 없이 고정된 결정적 흐름을 실행합니다:

1. **roster** — 반에 등록된 학생들을 id로 변환
2. **fill** — `record-class` 페이로드(점수가 있으면 `record-test-scores`도)를
   그 id와 입력 숫자로 채움
3. **apply** — 한 번의 백업된 원자적 트랜잭션으로 세션을 넣고, 자동 생성된 각
   학생의 출석·숙제 행을 UPDATE하며(빈 INSERT를 하지 않으므로 NULL 출석 행이
   생기지 않음), 점수를 기록

수업 하루치가 몇 초 만에 기록되고, ID·건수만 남기는 감사 행과 쓰기 전 자동 DB
백업이 따라옵니다.

### ClassCard 단어 세트 업로드

ClassCard 업로드는 자체 번들 브라우저로 돌아가므로(서드파티 플러그인 아님)
격리된 선생님 홈에서도 동작합니다. 보통은 한국어로 부탁하면 됩니다(예:
"이 단어들 클래스카드 〈반〉에 올려줘"). 수동 절차가 필요하면:

```powershell
# 1회: ClassCard 자격증명 저장 (프로필에만 저장 · 절대 저장소에 커밋 금지)
<cli> classcard login --username <id> --password <pw> --json
# 준비된 단어 세트를 반에 업로드 (headless)
<cli> classcard direct-upload --checkpoint <checkpoint.json> --class-url <ClassMain-url> --profile-root <profile-root> --json
```

`classcard verify` / `classcard recover`로 실행을 재확인하거나 이어서 진행할 수
있습니다. 자격증명과 브라우저 프로필은 비공개로 유지하세요.

### 에이전트가 한 일 검토 (세션 로그)

모든 Codex 세션은 비공개 검토 로그로 자동 기록됩니다(프롬프트, 에이전트 메시지와
도구 순서, 도구 인자·출력, 토큰 사용량, 턴별 모델·승인). 라이브 세션 성능에는
영향을 주지 않으며, 나중에 검토합니다:

```powershell
<cli> session-log list --profile-root <profile-root> --json
<cli> session-log show --session-id <id> --profile-root <profile-root> --json
```

`show`는 등록된 학습자 이름을 복원해서 보여 주고, `export`는 가린 채로
내보냅니다(`--reveal`로 해제). `session-log disable`/`enable`로 로깅을
일시중지·재개할 수 있습니다. 비밀값·토큰·경로는 항상 제거되고, 학습자 이름은
`privacy.json`에 등록된 경우에만 가려집니다. 자세한 내용:
[docs/session-logging.md](docs/session-logging.md).

### 단어장 보기

한국어로 부탁하면(예: "〈학생〉 단어장 진도 보여줘") 자연어 라우트가 비공개 DB에서
제공되는 **읽기 전용** 뷰어를 엽니다. 현재는 보기 전용이며, 단어 추가·임포트는
아직 명령 한 줄로 되는 흐름이 아닙니다.

### 예전에 손으로 넣은 행 보정

예전 날짜를 손으로 입력해 학생 출석이 NULL로 남았다면, 그 반·날짜로
`record-class`를 올바른 출석값으로 다시 실행하세요. `update_stub` 단계가 기존 행을
그 자리에서 채웁니다.

---

## 격리된 실제 사용 환경 (왜 필요한가)

다른 Codex 도구(전역 개발 플러그인, 멀티에이전트 오케스트레이터, 텔레메트리)도
함께 쓰는 선생님이라면, 그런 도구가 실제 수업 세션에 새어 들어오면 안 됩니다 —
단순한 작업을 느리게 만들고, 학습자 데이터 측면에서 프라이버시 문제이기도
합니다.

그래서 `bootstrap.ps1 -Mode User`는 **chat-lms 플러그인만** 로드하는 깨끗하고
격리된 선생님 `CODEX_HOME`과 전용 런처를 함께 만들어 줍니다(서드파티 플러그인
없음, 에이전트 오케스트레이션 매니페스토 병합 없음, 텔레메트리 없음). 개발자
본인의 `~/.codex`는 건드리지 않습니다. 선생님은 생성된 런처로 실제 세션을 띄우고,
설치된 나머지 도구는 다른 곳에서 그대로 잘 동작합니다.

**주의:** 개발 계정의 User/Machine 범위에 `CODEX_HOME`을 절대 설정하지 마세요 —
개발 세션에서 개발 도구가 빠집니다. 오버라이드는 선생님 런처 안에만 두세요.

---

## 개발

```bash
uv sync --dev
uv run pytest          # 전체 (~450 테스트, 격리됨)
uv run ruff check      # select=ALL
uv run basedpyright    # typeCheckingMode=all
```

품질 게이트: `pytest`, `ruff check`, `basedpyright`, 그리고 Windows 우선 CI
레인이 모두 통과해야 합니다. 저장소 프라이버시 스캔과 문서 계약 테스트가 모든
변경을 검증합니다.

CLI는 모든 명령이 안정적인 종료 코드 계약과 함께 한 줄 JSON을 출력합니다:
`0 PASS · 2 ERROR · 3 NEEDS_APPROVAL · 4 UNSAFE · 5 BLOCKED`.

---

## 더 읽어보기

- 구조 지도: [docs/architecture.md](docs/architecture.md)
- 제품 요구사항: [PRD.md](PRD.md)
- 용어 계약: [docs/terminology.md](docs/terminology.md)
- 계획 이력·상태: [plans/STATUS.md](plans/STATUS.md)
- 세션 로깅 상세: [docs/session-logging.md](docs/session-logging.md)
- 영어 README: [README.en.md](README.en.md)
