# Zeropark

OSS를 **설계 참고만** 하여 기능을 **네이티브로 재구현**한, 판매 가능한 단일 AI 워크스페이스
프레임워크. 한 프롬프트로 research·slides·sheets·browse·workflow·super-agent를 수행하고,
고객사별 배포본은 **Control Plane**으로 중앙 관리합니다.

> 엔진을 API로 호출하거나 외부 서비스로 띄우지 않습니다. 전부 한 리포·하나의 프레임워크에서
> 네이티브로 동작하므로, 클라이언트는 우리 프레임워크 하나만 설치하면 됩니다.

## 구조

```
packages/zeropark-core/      엔진 비의존 스파인: capabilities, models, provider, registry, router,
                             config(배포 프로파일), llm(멀티 프로바이더), netguard(SSRF), cache(Redis)
packages/zeropark-engines/   네이티브 엔진: crawl, search, slides(테마/PDF), sheets, browse,
                             browser_agent(LLM 브라우저 제어), workflow(DAG+관측성),
                             research / deep_research(Planner→Researcher→Reporter, HITL),
                             super_agent(3-phase 에이전트), rag, sandbox(Docker 격리)
packages/zeropark-web/       [프론트엔드] React 18 + Vite — 대화/워크플로/관리자 UI
services/gateway/            [백엔드] FastAPI — 라우팅, 인증(RBAC), SSE 스트리밍, 백그라운드 잡,
                             사용량 미터링, Control Plane 하트비트
services/control-plane/      [내부 운영용] 고객사 배포본 플릿 관리 — 라이선스, 상태 감시,
                             프로파일 원격 변경, 사용량 집계 대시보드 (고객 납품 금지)
docker-compose.yml           [인프라] Web + API + Redis + Qdrant
docs/                        제품/아키텍처/진행 문서
external/                    설계 참고용 OSS 체크아웃 (절대 import/실행하지 않음)
```

## 핵심 설계

- **Capability**: 제품 어휘(search/crawl/slides/research/super_agent/…)를 구현과 독립적으로 정의.
- **Provider(ABC)**: 엔진 1개 인터페이스. `cap_<capability>` 메서드로 디스패치, `stream()`으로 SSE 진행 이벤트 방출.
- **배포 프로파일**: `ZEROPARK_BRANDING__*`(화이트라벨), `ZEROPARK_FEATURES`(capability on/off)로
  고객사별 구성이 env 하나로 끝남. 포크 없는 커스터마이징.
- **Control Plane 연동**: 배포본이 주기적으로 하트비트(버전·capability·사용량)를 보고하고,
  응답으로 받은 프로파일을 **hot-reload** — 재배포 없이 원격 설정 변경.
- **MCP (Model Context Protocol)**: 외부 도구를 노드/에이전트 툴로 무한 확장.
- **멀티 LLM**: OpenAI 호환 + Anthropic(Claude). `ZEROPARK_LLM__PROVIDER`로 전환, native tool calling 지원.

## 빠른 시작 (Docker Compose)

**사전 요구사항 (Prerequisites)**
- Docker 및 Docker Compose가 설치되어 있어야 합니다.

```bash
cp .env.example .env          # ZEROPARK_LLM__API_KEY 등 설정
docker-compose up -d --build  # Web 80, API 8080, Qdrant 6333, Redis 6379
```

- **사용자 UI**: `http://localhost`
- **백엔드 API**: `http://localhost:8080` (프로파일: `GET /api/v1/profile`, 사용량: `GET /api/v1/usage`)

### Control Plane (내부 인프라 전용)

```bash
# 고객 납품 이미지에 절대 포함하지 말 것
# 1. 패키지 설치 (프로젝트 최상단에서 uv 사용)
uv sync

# 2. 환경변수 설정 및 실행 (Linux/Mac)
export ZEROPARK_CP_ADMIN_TOKEN=<random-token>
# (Windows CMD의 경우: set ZEROPARK_CP_ADMIN_TOKEN=<random-token>)

uvicorn zeropark_control.main:app --port 8090
# 브라우저: http://localhost:8090  → 배포 등록/라이선스 발급/상태·사용량 확인/프로파일 원격 편집
```

배포본 쪽에는 `.env`에 `ZEROPARK_CONTROL_PLANE__URL / DEPLOYMENT_ID / LICENSE_KEY`를 설정하면
하트비트가 시작됩니다.

## 주요 API

| 엔드포인트 | 설명 |
|---|---|
| `POST /api/v1/tasks` | 모드 기반 단발 작업 실행 |
| `POST /api/v1/tasks/stream` | SSE 실시간 진행 이벤트 (Thought/Action/Source/Artifact/Done) |
| `POST /api/v1/jobs` + `GET /api/v1/jobs/{id}/events` | 장시간 작업: DB 영속화 + 백그라운드 실행 + 재접속 가능한 SSE |
| `POST /api/v1/workflow/run` | DAG 워크플로 실행 (노드별 실행 로그 반환·영속화) |
| `GET /api/v1/workflow/runs` | 워크플로 실행 이력 (관측성) |
| `GET /api/v1/profile` | 배포 프로파일 (브랜딩 + 활성 capability) — 웹 부팅 시 화이트라벨링 |

## 구현 상태

| capability | 상태 | 구현 |
|---|---|---|
| crawl | ✅ | httpx + markdownify, SSRF 가드 (Native) |
| search | ✅ | Commodity API client (Native, SearXNG 미사용) |
| slides | ✅ | python-pptx + 테마/템플릿/스피커노트/이미지 + LibreOffice PDF (Native) |
| sheets | ✅ | openpyxl (Native) |
| browse | ✅ | Playwright 캡처 + **browser_agent**: LLM이 클릭/입력/탐색하는 제어 루프 (Native) |
| research | ✅ | **deep-research**: Planner→Researcher→Reporter, 인용, HITL 계획 검토 (Native) |
| super_agent | ✅ | 3-phase 에이전트 + native tool calling + 샌드박스/검색/크롤/MCP 도구 (Native) |
| workflow | ✅ | DAG 오케스트레이터: condition 분기·http·python·llm 노드, 노드별 실행 로그 (Native) |
| rag | ✅ | 임베딩 + Qdrant (Native) |

## 보안

- **SSRF 가드** (`zeropark_core.netguard`): URL을 DNS resolve 후 사설/루프백/링크로컬 대역 차단.
  crawl/browse/http 노드/브라우저 에이전트 전부 적용. 개발 시에만 `ZEROPARK_ALLOW_PRIVATE_URLS=1`.
- **샌드박스**: Python 실행은 네트워크 차단·메모리 제한·타임아웃 강제 kill의 일회용 Docker 컨테이너.
  Docker 없는 로컬 개발만 `ZEROPARK_ALLOW_UNSAFE_SANDBOX=1`로 in-process 폴백 허용(프로덕션 금지).
- **라이선스 게이트**: Control Plane에서 배포본 라이선스를 끄면 하트비트가 403으로 차단.

## 테스트

```bash
python -m pytest packages/zeropark-core packages/zeropark-engines services/gateway/tests services/control-plane/tests
```

`tests/test_auth.py`, `tests/test_rbac.py`는 게이트웨이를 :8000에 띄워야 하는 라이브 통합 테스트.

## 라이선스 (판매 시 필수)

OSS는 설계 참고가 기본. DeerFlow·browser-use(MIT), Presenton·Crawl4AI(Apache-2.0)는 attribution과
함께 코드 차용 가능. **Dify(상용 조건)·SearXNG(AGPL)는 소스 차용 금지** — 기능만 독립 재구현했고,
검색은 commodity API 클라이언트로 대체. 세부: `THIRD_PARTY_NOTICES.md`, `docs/oss-source-map.md`.
