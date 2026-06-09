# Zeropark

OSS를 **설계 참고만** 하여 기능을 **네이티브로 재구현**한, 판매 가능한 단일 AI 워크스페이스
프레임워크. 한 프롬프트로 crawl·slides·(예정)research·sheets·browse 등을 수행합니다.

> 엔진을 API로 호출하거나 외부 서비스로 띄우지 않습니다. 전부 한 리포·하나의 프레임워크에서
> 네이티브로 동작하므로, 클라이언트는 우리 프레임워크 하나만 설치하면 됩니다.

## 구조 (Enterprise 3-Tier Architecture)

Zeropark는 Dify와 같은 무거운 레거시를 버리고, 엔터프라이즈 환경에서 1초 만에 구동되는 극단적으로 가볍고 강력한 분산 환경을 제공합니다.

```
packages/zeropark-core/      엔진 비의존 스파인: capabilities, models, provider, registry, router, config, cache(Redis)
packages/zeropark-engines/   네이티브 구현: crawl, slides, search, workflow(React Flow 호환), mcp(Node.js 연동)
packages/zeropark-web/       [프론트엔드] React 18, Vite 기반의 최적화된 워크플로 및 대화 UI
services/gateway/            [백엔드] FastAPI 기반 얇고 빠른 API 및 Docker-in-Docker 샌드박스
docker-compose.yml           [인프라] Web + API + Redis(초고속 캐시) + Qdrant(영구 RAG 벡터 DB)
docs/                        제품/아키텍처/결정 문서
```

## 핵심 설계 (덧대도 스파게티가 안 되는 이유)

- **Capability**: 제품 어휘(search/crawl/slides/…)를 구현과 독립적으로 정의.
- **Provider(ABC)**: 엔진 1개 인터페이스. `cap_<capability>` 메서드로 디스패치.
- **MCP (Model Context Protocol)**: 무거운 하드코딩 없이 외부의 수천 가지 도구를 노드 1개로 무한 확장(Custom MCP 호환).
- **Cache-Aside Pattern**: Redis 기반으로 대화 로그와 워크플로를 캐싱하여 수십만 건의 대화도 1ms 만에 로드.
- 자세히: `docs/01-planning/architecture/architecture.md`, `.../dependency-isolation.md`.

## 빠른 시작 (Docker Compose)

모든 데이터베이스, 캐시, 프론트/백엔드는 도커 명령어 한 줄로 즉시 구동됩니다.

```bash
# 전체 시스템 구동 (Web 80, API 8080, Qdrant 6333, Redis 6379)
docker-compose up -d --build
```

### 브라우저 접속
- **사용자 UI**: `http://localhost`
- **백엔드 API**: `http://localhost:8080`

### 예: 백엔드 워크플로 엔진 (DAGOrchestrator & DockerSandbox) 사용법

Zeropark 코어 엔진은 노드 기반 워크플로를 안전하게 실행하기 위한 `DAGOrchestrator`와, 파이썬 코드 실행 시 엔터프라이즈급 격리를 보장하는 `DockerSandbox`를 내장하고 있습니다.

**1. 워크플로 파싱 및 실행 (DAGOrchestrator)**
```python
import asyncio
from zeropark_core.models_workflow import WorkflowDefinition, WorkflowNode, WorkflowEdge
from zeropark_engines.workflow import DAGOrchestrator

# 워크플로 정의 (프론트엔드의 React Flow JSON과 1:1 매핑)
definition = WorkflowDefinition(
    nodes=[
        WorkflowNode(id="node_1", type="input", data={"user_query": "안녕"}),
        WorkflowNode(id="node_2", type="llm", data={"prompt": "{{user_query}} 어떻게 지내?"})
    ],
    edges=[WorkflowEdge(id="e1", source="node_1", target="node_2")]
)

async def run_workflow():
    orchestrator = DAGOrchestrator(definition)
    # 위상 정렬(Topological Sort)에 따라 노드 순차 실행
    results = await orchestrator.execute(initial_inputs={"session_id": "123"})
    print(results)

asyncio.run(run_workflow())
```

**2. 컨테이너 격리 실행 (DockerSandbox)**
파이썬 노드 코드를 실행할 때 로컬 시스템을 보호하기 위해, 코드를 일회용(Ephemeral) 도커 컨테이너 안에서 실행하고 버립니다. (Docker in Docker 방식)

```python
from zeropark_engines.sandbox import DockerSandbox

# 네트워크 차단, 256MB 메모리 제한의 샌드박스 생성
sandbox = DockerSandbox(image="python:3.11-slim", mem_limit="256m", allow_network=False)

# 해킹 코드를 실행해도, 컨테이너 안에서만 돌고 시스템에 영향 없이 폐기됨
code_to_run = "import os; print('Securely listed:', os.listdir('/'))"
output = sandbox.execute(code_to_run)

print("결과:", output)
```

## 구현 상태

| capability | 상태 | 구현 |
|---|---|---|
| crawl | ✅ | httpx + markdownify (Native) |
| slides | ✅ | python-pptx (Native) |
| search | ✅ | Commodity API client (Native) |
| research | ✅ | LLM Multi-step reasoning (Native) |
| browse | ✅ | Playwright (Native) |
| sheets | ✅ | openpyxl (Native) |

## 라이선스 (판매 시 필수)

OSS는 설계 참고가 기본. DeerFlow·browser-use(MIT), Presenton·Crawl4AI(Apache-2.0)는 attribution과
함께 코드 차용 가능. **Dify(상용 조건)·SearXNG(AGPL)는 소스 차용 금지** — 기능만 독립 재구현.
세부: `THIRD_PARTY_NOTICES.md`.
