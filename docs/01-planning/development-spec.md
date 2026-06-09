---
doc_type: development_spec
project_id: zeropark
status: in_progress
owner: 홍수훈
updated_at: 2026-06-09
---

# 개발 명세서 (Zeropark)

## 1. 개발 목적

OSS 엔진들을 격리 통합하고, 그 위에 **엔진 비의존 제품 코어 + 어댑터 계층 + 얇은 게이트웨이**를
두어, Genspark형 AI 워크스페이스를 객체화된 형태로 구축한다. 기능을 계속 덧대도 구조가
무너지지 않고, 타 기업에 구축·판매할 수 있도록 패키징한다.

## 2. 모노레포 구조

```
zeropark/
  pyproject.toml          # uv 워크스페이스 루트 (external/* 제외)
  packages/
    zeropark-core/        # 엔진 비의존 스파인: capabilities, models, provider, registry, router, config
    zeropark-engines/     # NativeEngine + 네이티브 구현(crawl/slides/...) + loader
  services/
    gateway/              # 얇은 FastAPI (core/adapters에 위임)
    # web/ (Phase 3), workers/ (browser-use 등 격리 워커)
  external/               # OSS 설계 참고본 (import/실행 X, 워크스페이스 제외)
  docs/  scripts/  docker-compose.yml
```

## 3. 핵심 추상 (zeropark-core)

| 모듈 | 역할 |
|---|---|
| `capabilities.py` | 제품 어휘 Enum (search/crawl/research/slides/sheets/dashboard/browse/workflow/super_agent) |
| `models.py` | 정규화 계약: TaskRequest, TaskResult, Artifact, SourceRef, RunEvent, ProviderHealth |
| `provider.py` | Provider ABC. `cap_<capability>` 디스패치, 기본 stream/health |
| `registry.py` | 설정된 provider 런타임 색인, capability별 조회 |
| `router.py` | mode→capability 파이프라인(ModePlan) + capability→provider 선택 |
| `config.py` | ZeroparkSettings(pydantic-settings, .env/nested/per-tenant) + providers_from_env(레거시 호환) |
| `errors.py` | 타입드 에러 → 엣지에서 HTTP 코드 매핑 |

## 4. 엔진 계층 (zeropark-engines, 네이티브)

`NativeEngine` 상속 → in-process 구현. OSS는 import/호출하지 않고 설계 참고만.
LocalCrawlEngine(httpx+markdownify), PptxSlidesEngine(python-pptx)는 구현 완료. WebSearchEngine은
커머디티 검색 API 클라이언트(설정 시 등록). research/agent/browse/sheets/workflow는 계획.
`loader.build_registry`가 항상-온 엔진 + 설정형 엔진을 레지스트리에 등록.

## 5. 게이트웨이 API (services/gateway)

| Method | Endpoint | 설명 |
|---|---|---|
| GET | /health | 상태 + 설정된 provider/capability |
| GET | /providers | 런타임 provider 메타 |
| GET | /catalog | 정적 OSS 메타(repo/license/tier) |
| GET | /modes | mode→capability 파이프라인 |
| POST | /route | mode 계획(실행 X): capability별 선택 provider + missing |
| POST | /tasks | mode primary capability 실행 → 정규화 TaskResult |
| POST | /search /crawl /slides | capability 직접 실행(편의) |

## 6. 의존성 격리 (필수)

엔진을 import/호출하지 않고 네이티브 구현한다. 근거·전략: `architecture/dependency-isolation.md`.
제품 워크스페이스는 pydantic/httpx/fastapi만 의존하며 어떤 엔진도 import 하지 않는다.

## 7. 빌드/검증

```bash
# 제품 워크스페이스 (엔진과 분리된 가벼운 환경)
uv sync            # 또는 pip install -e packages/zeropark-core -e packages/zeropark-engines -e services/gateway
pytest packages services/gateway
uvicorn zeropark_gateway.main:app --port 8080
```

## 8. 주의사항

- `external/*`는 import/실행 금지(설계 참고만). 워크스페이스 멤버 금지.
- 라이선스 까다로운 엔진은 코어 아닌 교체형 어댑터 뒤에 둔다.
- Dify/SearXNG 소스 차용 금지. 차용(MIT/Apache) 시 THIRD_PARTY_NOTICES 표기.
