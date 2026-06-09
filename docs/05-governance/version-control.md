# 버전관리 규칙

## 1. 기본 원칙

1. `main` 브랜치에 직접 커밋하지 않는다.
2. 모든 작업은 Issue 또는 Task ID를 기준으로 시작한다.
3. 모든 작업은 기능 브랜치에서 진행한다.
4. 커밋 메시지에는 반드시 Task ID를 포함한다.
5. Merge Request 없이 `main`에 반영하지 않는다.
6. MR은 최소 1명 이상의 리뷰 후 병합한다.
7. 테스트 또는 Pipeline 실패 상태에서는 병합하지 않는다.
8. 배포 버전은 태그로 관리한다.
9. 변경사항은 `docs` 또는 `CHANGELOG.md`에 기록한다.
10. AI 코딩 도구가 수정하더라도 이 규칙은 반드시 지킨다.

## 2. 브랜치 전략

이 프로젝트는 GitLab Flow 기반으로 관리한다.

| 브랜치 | 용도 | 직접 커밋 |
|---|---|---|
| `main` | 운영 또는 배포 가능한 기준 브랜치 | 금지 |
| `develop` | 개발 통합 브랜치, 필요 시 사용 | 금지 |
| `feature/*` | 신규 기능 개발 | 허용 |
| `fix/*` | 버그 수정 | 허용 |
| `refactor/*` | 구조 개선 | 허용 |
| `docs/*` | 문서 변경 | 허용 |
| `hotfix/*` | 긴급 수정 | 허용 |
| `release/*` | 배포 준비 | 제한적 허용 |

## 3. 브랜치 네이밍 규칙

```bash
feature/DEV-001-login-api
fix/BUG-001-login-error
refactor/DEV-005-dashboard-structure
docs/DOC-001-project-docs
hotfix/HOTFIX-001-token-error
release/v1.0.0
```

좋은 예:

```bash
feature/DEV-001-gitlab-commit-api
fix/BUG-003-dashboard-loading-error
```

나쁜 예:

```bash
test
update
final
new-work
my-branch
```

## 4. 커밋 메시지 규칙

커밋 메시지는 Conventional Commits와 Task ID를 함께 사용한다.

```text
<type>(<scope>): [Task ID] <message>
```

예시:

```text
feat(project): [DEV-001] 프로젝트 목록 조회 API 추가
fix(gitlab): [BUG-001] GitLab webhook 중복 저장 오류 수정
docs(rule): [DOC-001] 브랜치 관리 규칙 추가
test(project): [DEV-001] 프로젝트 목록 API 테스트 추가
```

## 5. Type 규칙

| Type | 의미 |
|---|---|
| `feat` | 신규 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 |
| `style` | 포맷팅, 세미콜론, 공백 등 |
| `refactor` | 기능 변경 없는 구조 개선 |
| `test` | 테스트 추가 또는 수정 |
| `chore` | 빌드, 설정, 패키지 관리 |
| `ci` | CI/CD 설정 변경 |
| `perf` | 성능 개선 |
| `revert` | 이전 커밋 되돌림 |

## 6. 금지 커밋 메시지

```text
수정
업데이트
테스트
마지막
진짜최종
final
fix
change
```

## 7. 릴리즈 및 태그 규칙

이 프로젝트는 Semantic Versioning 형식을 따른다.

```text
vMAJOR.MINOR.PATCH
```

예시:

```text
v1.0.0
v1.1.0
v1.1.1
v2.0.0
```

| 변경 유형 | 버전 증가 |
|---|---|
| 기존 기능과 호환되지 않는 큰 변경 | MAJOR |
| 신규 기능 추가 | MINOR |
| 버그 수정 | PATCH |

태그 생성 예시:

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

## 8. 릴리즈 전 확인 사항

- [ ] `main` 브랜치 기준 최신 상태인가?
- [ ] 테스트가 통과했는가?
- [ ] MR 리뷰가 완료되었는가?
- [ ] `CHANGELOG.md` 또는 release note가 작성되었는가?
- [ ] 배포 방법이 문서화되었는가?

