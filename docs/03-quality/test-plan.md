---
doc_type: test_plan
project_id: ai-dashboard
status: draft
updated_at: 2026-05-19
---

# 테스트 계획서

## 1. 테스트 범위

- GitLab 커밋 조회
- GitLab Webhook 수신
- GitLab Merge Request 상태 조회
- GitLab Pipeline 상태 조회
- 개발자별 작업 현황 표시
- 프로젝트 진행률 계산
- 문서 템플릿 파싱
- 관리자 대시보드 화면 표시

## 2. 테스트 항목

| Test ID | 기능 | 테스트 내용 | 기대 결과 | 상태 |
|---|---|---|---|---|
| TEST-001 | GitLab 연동 | 커밋 발생 시 Webhook 수신 | 커밋 정보 저장 | not_started |
| TEST-002 | Task ID 매칭 | 커밋 메시지에서 Task ID 추출 | DEV-001 식별 | not_started |
| TEST-003 | 진행률 계산 | `docs/02-progress/progress.md` 기반 진행률 반영 | 대시보드에 표시 | not_started |
| TEST-004 | 개발자 활동 | 사용자별 커밋 목록 조회 | 개발자별 표시 | not_started |
| TEST-005 | Pipeline 연동 | Pipeline 실패 이벤트 수신 | 경고 표시 | not_started |

## 3. 테스트 결과

| 날짜 | Test ID | 결과 | 담당자 | 비고 |
|---|---|---|---|---|
| | | PASS / FAIL | | |
