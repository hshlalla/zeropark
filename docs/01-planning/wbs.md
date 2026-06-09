---
doc_type: wbs
project_id: zeropark_v2
status: in_progress
updated_at: 2026-06-09
---

# WBS (Zeropark V2 Enterprise)

## 1. 마일스톤 (Phase)

| Phase | 마일스톤 | 핵심 목표 | 상태 |
|---|---|---|---|
| 18 | **Docker 3-Tier 아키텍처 도입** | React + FastAPI + Qdrant + Redis의 엔터프라이즈 컨테이너 배포망 구축 | ✅ |
| 19 | **Custom MCP 지원** | 외부 Node.js 기반 MCP 서버를 워크플로 엔진에 네이티브로 연동 | ✅ |
| 20 | **Backend DB Persistence** | SQLite 기반 Repository 패턴으로 대화와 워크플로 데이터 영속성 확보 | ✅ |
| 21 | **Redis Cache-Aside 최적화** | Redis를 도입하여 병목구간(DB I/O) 제거 및 1ms 응답속도 확보 | ✅ |
| 22 | **채팅 렌더링 & LLM 토큰 최적화** | 프론트엔드 DOM 방어 및 백엔드 Context Truncation 도입 | ✅ |
| 23 | **Admin 대시보드 통계 파이프라인** | 백엔드 DB와 연동하여 총 워크플로 및 대화 횟수를 실시간 렌더링 | ✅ |
| 24 | **공식 문서 총정리 및 동기화** | `README.md`, `project.yml`, `architecture.md` 등에 신규 아키텍처 스펙 반영 | ✅ |

## 2. 작업 분해 (WBS 상세)

### Phase 18: Docker 3-Tier 아키텍처
| WBS | 작업 내용 | 상태 |
|---|---|---|
| 18-01 | `docker-compose.yml` 셋업 (Web, API, Qdrant, Redis) | ✅ |
| 18-02 | 프론트엔드 및 백엔드 포트 포워딩 및 통신 테스트 | ✅ |
| 18-03 | Docker-in-Docker 샌드박스 격리 기능 연동 | ✅ |

### Phase 19: Custom MCP & Workflow
| WBS | 작업 내용 | 상태 |
|---|---|---|
| 19-01 | MCP Client 연동 모듈 개발 | ✅ |
| 19-02 | 워크플로 DAG 노드에 MCP 툴(Node.js) 호출 로직 통합 | ✅ |

### Phase 20: Backend DB Persistence
| WBS | 작업 내용 | 상태 |
|---|---|---|
| 20-01 | `SQLAlchemy` 기반 `User`, `ChatSession`, `Workflow` 모델 설계 | ✅ |
| 20-02 | Repository 패턴 기반 CRUD 파이프라인 구축 | ✅ |

### Phase 21: Redis Caching
| WBS | 작업 내용 | 상태 |
|---|---|---|
| 21-01 | `redis-py` 클라이언트 및 싱글톤 매니저 구현 | ✅ |
| 21-02 | `ChatRepository` 에 Cache-Aside(캐시 우선) 패턴 적용 | ✅ |

### Phase 22~23: 성능 및 모니터링
| WBS | 작업 내용 | 상태 |
|---|---|---|
| 22-01 | `AppViewer.tsx` 에 `slice(-50)` 도입 (DOM 메모리 오버플로우 방어) | ✅ |
| 22-02 | `llm.py` 에 최근 10턴 Context Truncation 적용 (API 토큰 낭비 방어) | ✅ |
| 23-01 | `admin.py` 통계 API(`StatsResponse`)에 Workflow, Chat 누적 개수 집계 로직 추가 | ✅ |
| 23-02 | `Dashboard.tsx` 에 실시간 통계 표출용 Glass Panel UI 구현 | ✅ |

