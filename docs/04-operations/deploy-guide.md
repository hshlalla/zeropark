---
doc_type: deploy_guide
project_id: zeropark
status: in_progress
updated_at: 2026-06-09
---

# 배포 가이드 (Zeropark)

엔진이 네이티브이므로 **단일 아티팩트**만 배포한다. 외부 엔진 서비스가 없다.

## 1. 설치

```bash
pip install -e packages/zeropark-core -e packages/zeropark-engines -e services/gateway
# 또는 uv sync
```

요구: Python >=3.11. (참고 OSS `external/`는 배포에 포함하지 않는다.)

## 2. 설정 (클라이언트별 = 같은 코드 + 다른 .env)

`ZEROPARK_*` 환경변수 또는 `.env`(`.env.example` 참고):

| 변수 | 용도 |
|---|---|
| `ZEROPARK_OUTPUT_DIR` | 아티팩트 출력 폴더 |
| `ZEROPARK_LLM__*` | LLM 프로바이더/모델/키 (research·slides 콘텐츠·agent) |
| `ZEROPARK_SEARCH__BASE_URL` / `__API_KEY` | 커머디티 검색 백엔드(옵션) |
| `ZEROPARK_CAPABILITY_PREFERENCES` | capability별 선호 엔진 |

## 3. 실행

```bash
uvicorn zeropark_gateway.main:app --host 0.0.0.0 --port 8080
# 또는 Docker
docker compose up --build
```

확인: `GET /health` → 등록된 네이티브 엔진/capability.

## 4. 컨테이너

`docker-compose.yml`은 gateway 단일 서비스만 띄운다(엔진 서비스 없음). 이미지에는 core+engines+gateway가 설치된다.

## 5. 운영 점검

- `/health`로 엔진/capability 노출 확인.
- 아티팩트 출력 디렉터리 쓰기 권한.
- (Phase 5+) artifact store(Postgres/S3), 관측성(토큰·비용·트레이스).
