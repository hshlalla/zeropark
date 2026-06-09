# LLM 사용 정책

이 문서는 AI 코딩 도구와 LLM이 이 프로젝트 템플릿을 사용할 때 토큰 소모를 줄이고 문서 품질을 유지하기 위한 규칙입니다.

## 1. 기본 원칙

- 모든 문서를 매번 전부 읽지 않는다.
- 작업과 관련 있는 문서만 읽는다.
- 큰 문서는 필요한 섹션만 읽는다.
- 작업 결과는 코드 변경, 테스트 결과, 문서 변경이 연결되도록 남긴다.

## 2. 최소 확인 문서

대부분의 작업은 아래 문서만 먼저 확인한다.

```text
docs/project.yml
docs/01-planning/product-requirements.md
docs/01-planning/development-spec.md
docs/02-progress/progress.md
docs/05-governance/version-control.md
```

## 3. 작업별 추가 확인 문서

| 작업 | 추가 확인 문서 |
|---|---|
| 제품 방향 변경 | `docs/01-planning/product-requirements.md` |
| 시스템 구조 변경 | `docs/01-planning/architecture/architecture.md` |
| GitLab 이벤트 흐름 변경 | `docs/01-planning/architecture/system-flow.md` |
| 일정, 담당자, 범위 변경 | `docs/01-planning/wbs/wbs.md` |
| API 변경 | `docs/01-planning/api-spec.md` |
| 테스트 변경 | `docs/03-quality/test-plan.md` |
| 배포 변경 | `docs/04-operations/deploy-guide.md` |
| 릴리즈 준비 | `CHANGELOG.md`, `docs/04-operations/release-notes.md` |
| 대시보드 수집 규칙 변경 | `docs/05-governance/dashboard-integration.md` |

## 4. 문서 업데이트 기준

| 변경 내용 | 업데이트할 문서 |
|---|---|
| 제품 목표/사용자/성공 기준 변경 | `product-requirements.md`, `development-spec.md` |
| 기능 추가/삭제 | `product-requirements.md`, `development-spec.md`, `progress.md`, `CHANGELOG.md` |
| Task 상태 변경 | `progress.md`, 필요 시 `wbs.md` |
| 일정/담당자 변경 | `wbs.md`, `progress.md` |
| 구조 변경 | `architecture.md`, `system-flow.md`, `decision-log.md` |
| 테스트 추가/결과 변경 | `test-plan.md` |
| 배포 방식 변경 | `deploy-guide.md`, `release-notes.md` |
| 블로커 발생/해결 | `blockers.md`, 필요 시 `progress.md` |

## 5. 피해야 할 운영 방식

- 매 작업마다 `docs/**/*.md` 전체를 읽는 방식
- 작은 코드 수정마다 모든 문서를 갱신하는 방식
- 개발 노트를 너무 길게 남기는 방식
- 커밋 수만으로 진행률을 계산하는 방식
- LLM이 문서 구조를 임의로 바꾸는 방식
