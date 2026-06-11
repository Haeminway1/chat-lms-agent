---
name: chat-lms-onboarding
description: Use when setting up Chat LMS Agent for a teacher through Codex Desktop onboarding, sample workspace creation, schema memory, and zero-touch environment checks.
---

# Chat LMS Onboarding

Interview the teacher in Korean, prefer sample/dry-run setup first, and keep every setup action
inside Codex-run commands. Do not ask the teacher to edit files.

## Google Workspace (선택, 권장)

캘린더 일정 관리 · 단어시험지 시트/드라이브 업로드 · 학부모 메일 발송에 쓰입니다.
원칙: 사용자는 인증(로그인·동의)만 하고, 나머지는 전부 자동으로 처리합니다.

1. `python -m chat_lms_agent gws status --json` 으로 연동 여부 확인.
2. 미연동이면 권한 4가지(캘린더 일정, 시트, 앱이 만든 드라이브 파일, 메일 발송만)를
   한 문장으로 설명하고 `python -m chat_lms_agent gws setup --json` 실행 —
   브라우저가 한 번 열리고 Google 동의 후 자동으로 끝납니다 (내장 기본 클라이언트
   사용 시 이게 전부).
3. setup 이 `GWS_CLIENT_MISSING` 을 내면 (자체 클라이언트가 필요한 경우):
   사용자에게 콘솔 절차를 시키지 말 것. 에이전트가 브라우저 자동화로 직접 진행한다 —
   사용자는 Google 로그인만. 순서: console.cloud.google.com → 프로젝트 생성 →
   "API 및 서비스 > OAuth 동의 화면" 구성(외부, 앱 이름만; **게시 상태를 '프로덕션'으로**
   — 테스트 모드면 7일마다 재로그인 필요) → "사용자 인증 정보 > OAuth 클라이언트 ID >
   데스크톱 앱" 생성 → JSON 다운로드. 그 다음
   `python -m chat_lms_agent gws client install --json` 이 다운로드 폴더에서 자동으로
   찾아 설치하고, 이어서 `gws setup` 실행. (이 한정된 콘솔 작업은 Workspace 라우트의
   브라우저 금지 예외 — 업무 데이터 작업은 여전히 CLI만 사용.)
4. 배지(토큰)는 사용자 홈 `.chat_lms_agent/google_token.json` 에 저장됨 — 레포/문맥에
   절대 넣지 말 것. 완료되면 `tool:gws` 기억에 연동 완료와 자주 쓰는 폴더/시트를 기록.
5. 건너뛰어도 됩니다 — doctor 의 gws 행이 나중에 다시 안내합니다. 메일 발송은 항상
   교사 승인(approval) 후에만 가능합니다.
