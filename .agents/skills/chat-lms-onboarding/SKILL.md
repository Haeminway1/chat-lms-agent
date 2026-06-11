---
name: chat-lms-onboarding
description: Use when setting up Chat LMS Agent for a teacher through Codex Desktop onboarding, sample workspace creation, schema memory, and zero-touch environment checks.
---

# Chat LMS Onboarding

Interview the teacher in Korean, prefer sample/dry-run setup first, and keep every setup action
inside Codex-run commands. Do not ask the teacher to edit files.

## Google Workspace (선택, 권장)

캘린더 일정 관리 · 단어시험지 시트/드라이브 업로드 · 학부모 메일 발송에 쓰입니다.

1. `python -m chat_lms_agent gws status --json` 으로 연동 여부 확인.
2. 미연동이면 권한 4가지(캘린더 일정, 시트, 앱이 만든 드라이브 파일, 메일 발송만)를
   한 문장으로 설명하고 `python -m chat_lms_agent gws setup --json` 실행 —
   브라우저가 한 번 열리고 Google 동의 후 자동으로 끝납니다.
3. 배지(토큰)는 사용자 홈 `.chat_lms_agent/google_token.json` 에 저장됨 — 레포/문맥에
   절대 넣지 말 것. 완료되면 `tool:gws` 기억에 연동 완료와 자주 쓰는 폴더/시트를 기록.
4. 건너뛰어도 됩니다 — doctor 의 gws 행이 나중에 다시 안내합니다. 메일 발송은 항상
   교사 승인(approval) 후에만 가능합니다.
