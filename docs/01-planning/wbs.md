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
| 1 | **인프라 & 보안 컨테이너** | PostgreSQL DB 셋업, OAuth 로그인, Docker 샌드박스 격리 | ⏳ |
| 2 | **RBAC & Admin 대시보드** | 사용자 권한(Admin/User) 분리, 토큰 모니터링 Admin 페이지 구성 | ⏳ |
| 3 | **Advanced RAG (Knowledge Base)** | 벡터 DB(Milvus 등) 연동, UI 기반 문서 업로드 및 청킹 제어 | ⏳ |
| 4 | **Visual Workflow Builder** | React Flow 기반 다중 에이전트 노드 에디터 구축 | ⏳ |
| 5 | **Ecosystem (MCP & IM)** | MCP HTTP/SSE 배포, Slack/Teams 봇 연동 및 스킬 시스템 플러그인화 | ⏳ |

## 2. 작업 분해 (WBS 상세)

### Phase 1: 인프라 & 보안 컨테이너
| WBS | 작업 내용 | 담당 | 상태 |
|---|---|---|---|
| 2-01 | PostgreSQL DB 연동 (SQLAlchemy / Alembic) | - | ⏳ |
| 2-02 | OAuth 2.0 (Google 등) 소셜 로그인 구현 | - | ⏳ |
| 2-03 | Docker 기반 파이썬 샌드박스 엔진(`DockerSandbox`) 구현 | - | ⏳ |

### Phase 2: RBAC & Admin 대시보드
| WBS | 작업 내용 | 담당 | 상태 |
|---|---|---|---|
| 2-04 | User / Workspace / Role 데이터 모델 설계 | - | ⏳ |
| 2-05 | FastAPI 전역 권한 인증 미들웨어(Middleware) 추가 | - | ⏳ |
| 2-06 | Admin 전용 대시보드 UI (사용자 관리, 비용 통계) | - | ⏳ |

### Phase 3: Advanced RAG
| WBS | 작업 내용 | 담당 | 상태 |
|---|---|---|---|
| 2-07 | Milvus / Qdrant VectorDB 컨테이너 세팅 | - | ⏳ |
| 2-08 | 프론트엔드 문서 업로드 화면 및 파싱(청크/오버랩) 튜닝 UI | - | ⏳ |
| 2-09 | 문서 접근 권한(ACL) 필터링이 적용된 하이브리드 검색 구현 | - | ⏳ |

### Phase 4: Visual Workflow Builder (Dify 스타일)
| WBS | 작업 내용 | 담당 | 상태 |
|---|---|---|---|
| 2-10 | React Flow 프론트엔드 캔버스 및 노드 컴포넌트 개발 | - | ⏳ |
| 2-11 | 백엔드 동적 라우터 및 DAG(Directed Acyclic Graph) 파서 구현 | - | ⏳ |

### Phase 5: Ecosystem
| WBS | 작업 내용 | 담당 | 상태 |
|---|---|---|---|
| 2-12 | MCP 클라이언트/서버 HTTP SSE 통신 모듈 확장 | - | ⏳ |
| 2-13 | Slack App 연동 봇 서버 작성 | - | ⏳ |
| 2-14 | 스킬 마켓플레이스 레지스트리 구조 확립 | - | ⏳ |
