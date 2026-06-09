# AI 개발 작업 지침

이 파일은 사람 개발자와 AI 코딩 에이전트가 함께 따르는 프로젝트 작업 규칙입니다. 모든 LLM 기반 개발 도구는 코드 수정 전에 이 파일과 `docs/` 문서를 먼저 확인해야 합니다.

## 1. 기본 원칙

- 이 프로젝트의 코드는 반드시 Git 버전관리 규칙을 따른다.
- 모든 작업은 Task ID 또는 Issue ID를 기준으로 진행한다.
- 모든 코드 변경은 목적, 영향 범위, 테스트 방법을 함께 남긴다.
- 기존 코드 스타일, 폴더 구조, API 계약을 우선 존중한다.
- 요청 범위 밖의 대규모 구조 변경을 임의로 진행하지 않는다.
- 불확실한 요구사항은 최소 변경으로 처리하고, 필요한 경우 질문 또는 결정 기록을 남긴다.
- 보안 정보, 토큰, 비밀번호, private key를 코드나 문서에 직접 작성하지 않는다.

## 2. 문서 확인 원칙

AI 에이전트는 모든 문서를 매번 전부 읽지 않는다. 먼저 최소 문서를 확인하고, 작업 범위에 따라 필요한 문서만 추가로 읽는다.

### 항상 확인하는 최소 문서

1. `docs/project.yml`
2. `docs/01-planning/product-requirements.md`
3. `docs/01-planning/development-spec.md`
4. `docs/02-progress/progress.md`
5. `docs/05-governance/version-control.md`

### 작업 범위별 추가 확인 문서

| 작업 범위 | 추가 확인 문서 |
|---|---|
| 제품 목적, 사용자, 기능 범위 변경 | `docs/01-planning/product-requirements.md` |
| 아키텍처, 데이터 흐름, 외부 연동 | `docs/01-planning/architecture/architecture.md`, `docs/01-planning/architecture/system-flow.md` |
| 일정, 담당자, 작업 분해 | `docs/01-planning/wbs/wbs.md` |
| API 변경 | `docs/01-planning/api-spec.md` |
| 테스트 추가 또는 실패 수정 | `docs/03-quality/test-plan.md` |
| 배포, 환경 변수, 운영 변경 | `docs/04-operations/deploy-guide.md`, `docs/04-operations/release-notes.md` |
| 대시보드 수집 규칙 변경 | `docs/05-governance/dashboard-integration.md` |
| 설계 결정, 정책 변경, 되돌리기 어려운 선택 | `docs/01-planning/decision-log.md` |
| 이전 작업 맥락 확인 | `docs/02-progress/notes/`에서 관련 Task ID 파일만 |

### 토큰 사용 규칙

- 관련 없는 문서를 전부 읽지 않는다.
- 큰 문서는 필요한 섹션만 확인한다.
- `docs/02-progress/notes/`는 전체 스캔하지 않고 관련 Task ID 또는 날짜 파일만 확인한다.
- 변경 후에는 수정한 문서와 직접 연결된 참조 문서만 업데이트한다.
- 대시보드가 파싱하는 정형 파일은 `docs/project.yml`, `docs/01-planning/wbs/wbs.md`, `docs/02-progress/progress.md`, `docs/02-progress/blockers.md`를 우선으로 한다.

## 3. 브랜치 규칙

새 작업은 반드시 아래 형식의 브랜치에서 진행한다.

```bash
feature/DEV-000-description
fix/BUG-000-description
refactor/DEV-000-description
docs/DOC-000-description
hotfix/HOTFIX-000-description
release/v1.0.0
```

금지 브랜치명:

```text
test
update
final
new
temp
my-branch
```

## 4. 커밋 메시지 규칙

커밋 메시지는 Conventional Commits와 Task ID를 함께 사용한다.

```text
<type>(<scope>): [Task ID] <message>
```

예시:

```text
feat(auth): [DEV-001] 로그인 API 구현
fix(dashboard): [BUG-002] 진행률 계산 오류 수정
docs: [DOC-001] 개발 문서 업데이트
refactor(api): [DEV-003] GitLab API 클라이언트 구조 개선
test(auth): [DEV-001] 로그인 API 테스트 추가
```

허용 type:

```text
feat, fix, docs, style, refactor, test, chore, ci, perf, revert
```

금지 메시지:

```text
수정
업데이트
테스트
final
마지막
진짜최종
fix
change
```

## 5. 코드 변경 규칙

- 요청받은 범위 외의 파일은 수정하지 않는다.
- 불필요한 리팩토링을 하지 않는다.
- 기존 함수명, API 경로, DB 스키마를 임의로 변경하지 않는다.
- 변경이 필요한 경우 `docs/01-planning/decision-log.md`에 이유와 영향 범위를 남긴다.
- `.env`, secret, private key 파일을 생성하거나 커밋하지 않는다.
- 테스트 가능한 단위로 작게 변경한다.
- 관리 대시보드가 읽는 문서 스키마를 변경할 때는 `docs/05-governance/dashboard-integration.md`도 함께 수정한다.
- 제품 목표, 사용자, 핵심 기능, 제외 범위가 바뀌면 `docs/01-planning/product-requirements.md`를 함께 갱신한다.
- 기능, API, 테스트, 배포에 영향을 주는 변경은 관련 문서를 함께 갱신한다.
- 구조, 데이터 흐름, 외부 연동이 바뀌면 `docs/01-planning/architecture/` 문서와 Mermaid 다이어그램을 함께 갱신한다.
- 작업 범위, 일정, 담당자가 바뀌면 `docs/01-planning/wbs/wbs.md`와 `docs/02-progress/progress.md`를 함께 갱신한다.
- 릴리즈에 포함될 사용자 영향 변경은 `CHANGELOG.md`와 `docs/04-operations/release-notes.md`에 반영한다.
- 작업 중 판단, 보류, 우회, 블로커는 `docs/02-progress/notes/` 또는 `docs/01-planning/decision-log.md`에 남긴다.

## 6. 작업 완료 조건

작업 완료 전 아래 항목을 확인한다.

- Task ID가 있는가?
- 브랜치명이 규칙에 맞는가?
- 커밋 메시지가 규칙에 맞는가?
- 관련 문서가 업데이트되었는가?
- 테스트 방법 또는 확인 방법이 작성되었는가?
- 기존 기능을 깨지 않았는가?
- MR 설명이 작성되었는가?
- secret 정보가 포함되지 않았는가?

## 7. AI 작업 보고 형식

AI 에이전트는 작업 후 아래 형식으로 요약한다.

```md
## 작업 요약

- Task ID:
- 변경 목적:
- 변경 파일:
- 주요 변경 내용:
- 테스트 방법:
- 주의사항:
- 다음 작업:
```

## 8. 절대 금지 사항

- Task ID 없는 커밋
- 의미 없는 커밋 메시지
- 테스트 없이 완료 처리
- secret 정보 커밋
- 임의의 대규모 구조 변경
- 기존 문서 무시
- 실패한 테스트 숨기기
