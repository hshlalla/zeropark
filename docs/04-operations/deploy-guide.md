---
doc_type: deploy_guide
project_id: ai-dashboard
status: draft
updated_at: 2026-05-19
---

# 배포 가이드

## 1. 실행 환경

| 항목 | 내용 |
|---|---|
| Frontend | React / Next.js |
| Backend | FastAPI / Node.js 중 선택 |
| Database | PostgreSQL |
| Git 연동 | GitLab API / Webhook |
| 배포 방식 | Docker Compose |

## 2. 환경 변수

```env
GITLAB_BASE_URL=https://gitlab.company.com
GITLAB_PRIVATE_TOKEN=
GITLAB_WEBHOOK_SECRET=
DATABASE_URL=
```

## 3. 로컬 실행

```bash
docker compose up -d
```

## 4. 배포 절차

1. `main` 브랜치 최신화
2. 환경 변수 확인
3. Docker 이미지 빌드
4. 컨테이너 실행
5. GitLab Webhook 테스트
6. 관리자 대시보드 접속 확인

## 5. 롤백 방법

```bash
docker compose down
docker compose up -d
```

