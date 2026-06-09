---
doc_type: architecture
project_id: zeropark_v2
status: drafting
updated_at: 2026-06-09
---

# Zeropark V2 Enterprise Architecture

## 1. 개요
Zeropark V2는 단순한 로컬 챗봇 엔진을 넘어, **Docker 3-Tier 아키텍처(Web, API, Cache/DB)** 기반의 분산 엔터프라이즈 플랫폼으로 진화했습니다. 극강의 보안(Docker Sandbox)과 속도(Redis Cache-Aside)를 보장합니다.

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

    Agent --> DockerSandbox
    RAG --> VectorDB
    Gateway --> Redis
    Gateway --> DB
```

## 3. 핵심 변경 사항 (V1 -> V2)

### 3.1. Docker 3-Tier 아키텍처 도입
- 프론트엔드(React), 백엔드(FastAPI), 캐시(Redis), 벡터DB(Qdrant)가 각각 독립적인 컨테이너로 동작하며 `docker-compose` 로 즉시 스핀업됩니다.

### 3.2. Redis Cache-Aside Pattern
- DB(SQLite)의 병목을 막기 위해 모든 채팅 세션 및 워크플로 메타데이터는 1차적으로 Redis에 읽기/쓰기를 수행(Cache-Aside)하여 1ms 응답속도를 달성합니다.

### 3.3. Custom MCP (Model Context Protocol) 지원
- 외부 툴을 무겁게 파이썬 코드로 이식할 필요 없이, 외부 Node.js 기반 MCP 서버를 워크플로 노드 중 하나로 즉각 연결하여 기능을 무한 확장합니다.

### 3.4. Sandbox 네트워크 차단 (Docker-in-Docker)
- 에이전트가 생성한 Python 코드는 호스트 네트워크와 완벽히 차단된(Memory Limited, Network Disabled) 일회용 도커 컨테이너에서만 실행되고 즉각 폐기됩니다.
