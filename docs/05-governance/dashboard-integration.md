# 대시보드 연동 규칙

이 문서는 관리 대시보드가 프로젝트를 자동 수집할 때 따르는 데이터 계약입니다.

## 1. 수집 우선순위

관리 대시보드는 아래 순서로 데이터를 읽습니다.

1. `docs/project.yml`
2. `docs/01-planning/product-requirements.md`
3. `docs/02-progress/progress.md`
4. `docs/01-planning/wbs/wbs.md`
5. `docs/01-planning/architecture/architecture.md`
6. `docs/01-planning/architecture/system-flow.md`
7. GitLab Push, Merge Request, Comment, Pipeline Webhook 이벤트
8. GitLab REST API
9. GitLab Commits API
10. GitLab Issues API

## 2. 추적 파일

GitLab에 push가 발생하면 대시보드는 변경 파일 목록을 보고 아래 파일을 우선 추적합니다.

| 파일 | 추적 이유 | 변경 시 업데이트할 대시보드 영역 |
|---|---|---|
| `docs/project.yml` | 프로젝트 기본 정보와 GitLab 연결 정보 | 프로젝트 카드, 담당자, 상태, 경고 규칙 |
| `docs/01-planning/product-requirements.md` | 제품 목적, 사용자, 핵심 기능, 성공 기준 | 제품 개요, 범위 변경 |
| `docs/01-planning/development-spec.md` | 기능 범위와 주요 기능 목록 | 기능 현황, 요구사항 변경 |
| `docs/01-planning/architecture/architecture.md` | 시스템 구성과 컴포넌트 | 아키텍처 탭, 영향 범위 |
| `docs/01-planning/architecture/system-flow.md` | 이벤트/데이터 흐름 | 연동 흐름, 장애 분석 |
| `docs/01-planning/wbs/wbs.md` | 마일스톤, 일정, 작업 분해 | WBS, 일정, 지연 작업 |
| `docs/02-progress/progress.md` | 작업 상태와 진행률 | 진행률, Task 현황 |
| `docs/02-progress/blockers.md` | 블로커와 리스크 | 블로커 카드, 경고 |
| `docs/03-quality/test-plan.md` | 테스트 계획과 결과 | 테스트 상태, 품질 지표 |
| `docs/04-operations/release-notes.md` | 릴리즈 요약 | 릴리즈 카드 |
| `CHANGELOG.md` | 변경 이력 | 변경사항 타임라인 |
| `docs/01-planning/decision-log.md` | 주요 결정 | 의사결정 로그 |
| `docs/02-progress/notes/**/*.md` | 개발 노트 | 활동 기록, 작업 맥락 |

### 최소 필수 추적 파일

처음 구현할 때는 아래 파일만 추적해도 대시보드 기본 화면을 만들 수 있습니다.

```text
docs/project.yml
docs/01-planning/product-requirements.md
docs/01-planning/wbs/wbs.md
docs/02-progress/progress.md
docs/02-progress/blockers.md
CHANGELOG.md
```

## 3. GitLab 이벤트 추적

| 이벤트 | 수집 데이터 | 대시보드 업데이트 |
|---|---|---|
| Push | commit hash, message, author, branch, changed files | 최근 커밋, 문서 변경, Task 활동일 |
| Merge Request | title, source branch, target branch, state, reviewers | 리뷰 상태, MR 상태, 진행률 |
| Comment | note body, author, target type | 리뷰 코멘트, 블로커 후보 |
| Pipeline | status, ref, sha, duration | 테스트 상태, 배포 가능 여부 |
| Tag | tag name, commit sha, message | 릴리즈 상태, 릴리즈 노트 |

## 4. 핵심 카드 데이터

| 카드 항목 | 기본 데이터 소스 | 보조 데이터 소스 |
|---|---|---|
| 프로젝트명 | `docs/project.yml` | GitLab project |
| 담당자 | `docs/project.yml` | GitLab members |
| 현재 상태 | `docs/project.yml`, `docs/02-progress/progress.md` | Issue, MR |
| 진행률 | `docs/02-progress/progress.md` | MR, Issue, Pipeline |
| 최근 커밋일 | GitLab commits | Webhook event log |
| 최근 문서 수정일 | Git commit | 파일 mtime |
| 진행 중 Task 수 | `docs/01-planning/wbs/wbs.md`, `docs/02-progress/progress.md` | GitLab issues |
| 완료 Task 수 | `docs/01-planning/wbs/wbs.md`, `docs/02-progress/progress.md` | GitLab issues |
| 블로커 수 | `docs/02-progress/progress.md` | Issue label |
| 지연 여부 | 목표일 비교 | MR, Issue inactivity |
| 릴리즈 상태 | `docs/04-operations/release-notes.md`, `CHANGELOG.md` | GitLab tag |

## 5. Task ID 매칭

Task ID는 브랜치명, 커밋 메시지, MR 제목, Issue 제목에서 추출합니다.

허용 형식:

```text
DEV-001
BUG-001
DOC-001
HOTFIX-001
```

커밋 메시지 권장 형식:

```text
feat(gitlab): [DEV-001] GitLab 커밋 수집 API 구현
```

브랜치명 권장 형식:

```text
feature/DEV-001-gitlab-commits
fix/BUG-001-commit-fetch-error
```

## 6. GitLab Webhook 처리 원칙

Webhook은 실시간 이벤트 반영에 사용합니다.

- Push Event: 커밋, 브랜치, 작성자, Task ID 추출
- Push Event changed files: 추적 파일 변경 여부 확인
- Merge Request Event: 리뷰 상태, merge 상태, 지연 여부 계산
- Comment Event: 리뷰 코멘트와 블로커 신호 수집
- Pipeline Event: 테스트 성공, 실패, 배포 가능 여부 반영
- Tag Event: 릴리즈 노트와 변경 이력 연결

Webhook 이벤트는 누락될 수 있으므로, 주기적으로 GitLab API 재조회로 보정합니다.

## 7. GitLab API 재조회 원칙

아래 상황에서는 API로 다시 조회합니다.

- 대시보드 최초 프로젝트 등록
- Webhook 장애 복구
- 특정 기간별 커밋 재계산
- 진행률 재산정
- 관리자 수동 새로고침

권장 조회 대상:

- Commits API
- Merge Requests API
- Issues API
- Pipelines API
- Project Members API

## 8. 진행률 계산 권장식

진행률은 프로젝트별로 조정할 수 있지만 기본값은 아래 비중을 사용합니다.

| 항목 | 비중 |
|---|---:|
| 기능 체크리스트 완료율 | 35% |
| Merge Request 상태 | 25% |
| 테스트 및 Pipeline 상태 | 20% |
| Issue 상태 | 10% |
| 문서 업데이트 상태 | 5% |
| 배포 준비 상태 | 5% |

## 9. 경고 조건

대시보드는 아래 조건을 경고로 표시합니다.

- 3일 이상 커밋 없음
- 5일 이상 `docs/02-progress/progress.md` 업데이트 없음
- 목표일이 지났지만 Task가 `done`이 아님
- MR이 3일 이상 review 상태로 정체
- Pipeline 실패 상태가 유지됨
- Task ID 없는 커밋 또는 브랜치 발견
- 필수 문서 누락

## 10. 운영 주의사항

이 대시보드는 감시 도구가 아니라 프로젝트 리스크를 조기에 발견하기 위한 운영 도구입니다.

커밋 수만으로 개발자 평가를 하지 않으며, 설계, 리뷰, 테스트, 문서화, 장애 대응 같은 활동을 함께 봅니다.
