---
doc_type: architecture
project_id: zeropark_v2
status: drafting
updated_at: 2026-06-10
---

# Zeropark V2 Enterprise Architecture

## 1. 개요
Zeropark V2는 단순한 로컬 챗봇 엔진을 넘어, **Docker 3-Tier 아키텍처(Web, API, Cache/DB)** 기반의 분산 엔터프라이즈 플랫폼으로 진화했습니다. 극강의 보안(Docker Sandbox, SSRF 가드)과 속도(Redis Cache-Aside)를 보장하며, 고객사별 배포본은 별도의 **Control Plane**(자사 인프라 전용)에서 라이선스·상태·프로파일·사용량을 중앙 관리합니다.

## 2. 시스템 구성도

```mermaid
flowchart TD
    subgraph Client [Client Tier]
        WebUI[React 18 / Vite Web App]
        SlackBot[Slack/Teams IM Bot]
        MCPClient[External MCP Clients]
    end

    subgraph API [API Gateway / Auth]
        Gateway[FastAPI Gateway (Port 8080)]
        Auth[RBAC / OAuth Service]
        Gateway --> Auth
    end

    subgraph Core [Zeropark V2 Core Engines]
        Router[Workflow Router & React Flow DAG]
        Agent[Multi-Agent Orchestrator]
        RAG[RAG & Chunking Engine]
        MCPNode[Node.js Custom MCP Adapter]
    end

    subgraph Sandbox [Isolated Environment]
        DockerSandbox[Docker-in-Docker Security Sandbox]
    end

    subgraph Data [Data Tier]
        DB[(SQLite / RDBMS)]
        Redis[(Redis Cache / Port 6379)]
        VectorDB[(Qdrant Vector DB / Port 6333)]
    end

    Client --> Gateway
    Gateway --> Router
    Router --> Agent
    Router --> RAG
    Router --> MCPNode

    subgraph Fleet [Control Plane - 자사 인프라 전용]
        CP[Control Plane API + Dashboard / Port 8090]
        CPDB[(Deployments / Licenses / Usage)]
        CP --> CPDB
    end

    Agent --> DockerSandbox
    RAG --> VectorDB
    Gateway --> Redis
    Gateway --> DB
    Gateway -. "heartbeat: 버전·capability·사용량" .-> CP
    CP -. "응답: 프로파일 (hot-reload)" .-> Gateway
```

## 3. 핵심 변경 사항 (V1 -> V2)

### 3.1. Docker 3-Tier 아키텍처 도입
- 프론트엔드(React), 백엔드(FastAPI), 캐시(Redis), 벡터DB(Qdrant)가 각각 독립적인 컨테이너로 동작하며 `docker-compose` 로 즉시 스핀업됩니다.

### 3.2. Redis Cache-Aside Pattern
- DB(SQLite)의 병목을 막기 위해 모든 채팅 세션 및 워크플로 메타데이터는 1차적으로 Redis에 읽기/쓰기를 수행(Cache-Aside)하여 1ms 응답속도를 달성합니다.

### 3.3. Custom MCP (Model Context Protocol) 지원
- 외부 툴을 무겁게 파이썬 코드로 이식할 필요 없이, 외부 Node.js 기반 MCP 서버를 워크플로 노드 중 하나로 즉각 연결하여 기능을 무한 확장합니다.

### 3.4. Sandbox 네트워크 차단 (Docker-in-Docker)
- 에이전트가 생성한 Python 코드는 호스트 네트워크와 완벽히 차단된(Memory Limited, Network Disabled) 일회용 도커 컨테이너에서만 실행되고 즉각 폐기됩니다. 코드는 셸을 거치지 않고 argv로 전달되며, 타임아웃 초과 시 강제 kill 됩니다. Docker 미가용 시 in-process 폴백은 `ZEROPARK_ALLOW_UNSAFE_SANDBOX=1` 명시 opt-in일 때만 허용됩니다(프로덕션 금지).

### 3.5. SSRF 가드 (netguard)
- 사용자 입력 URL(crawl/browse/http 노드/브라우저 에이전트)은 `zeropark_core.netguard`가 DNS resolve 후 사설·루프백·링크로컬·예약 대역을 차단합니다. 문자열 블랙리스트가 아닌 주소 기반 검증이라 `127.1` 등 우회 표기도 막습니다.

### 3.6. 배포 프로파일 (고객사 커스터마이징, 포크 금지 원칙)
- `ZEROPARK_BRANDING__*`(제품명/로고/색/고객사명)과 `ZEROPARK_FEATURES`(capability별 on/off)로 고객사 구성을 결정합니다. 꺼진 capability는 엔진 등록 자체가 생략되어 표면적이 줄어듭니다. 웹은 부팅 시 `GET /api/v1/profile`로 화이트라벨링합니다.

### 3.7. Control Plane (플릿 관리, 고객 납품 금지)
- `services/control-plane`은 자사 인프라에서만 구동: 배포 등록 → 라이선스 키 발급 → 하트비트 기반 online/offline 감시 → 대시보드에서 프로파일 원격 편집(다음 하트비트에 hot-reload 적용) → 라이선스 차단 스위치.
- 게이트웨이 하트비트에는 버전·활성 capability·**사용량 스냅샷**(작업 수/실패/토큰/capability별)이 실립니다. Control Plane 장애는 제품 동작에 영향을 주지 않습니다(fire-and-forget).

### 3.8. 멀티 LLM + 에이전트 코어
- `BaseLLMClient` 추상화 위에 OpenAI 호환·Anthropic 어댑터. async/토큰 스트리밍/native tool calling 지원, 오래된 컨텍스트는 다이제스트로 압축.
- SuperAgent는 Planner→Researcher→Reporter 3-phase, DeepResearch는 섹션별 검색·크롤·인용 + HITL(계획 검토 후 재개, `PAUSED` 상태)을 지원합니다. 진행 상황은 RunEvent로 SSE 스트리밍됩니다.
