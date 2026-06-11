---
doc_type: progress
project_id: zeropark_v2
status: in_progress
updated_at: 2026-06-10
---

# 진척 상황 (Zeropark V2 Enterprise)

기존 V1(PoC) 버전 개발을 100% 완료하고, 새로운 B2B 상용화(Enterprise) 규격인 V2 개발을 새롭게 시작합니다.

## 최근 완료된 작업
- **Phase 18**: Docker 3-Tier 아키텍처 (Gateway API + React Web + Qdrant + Redis) 및 Docker-in-Docker Sandbox 연동 완료.
- **Phase 19**: Custom MCP (Model Context Protocol) 지원. Node.js 엔진 연동으로 무한 확장 플러그인 생태계 구축.
- **Phase 20**: Backend DB Persistence. SQLite 기반 Repository 패턴을 도입하여 ChatSession과 Workflow 영구 보존.
- **Phase 21**: Redis Caching. Cache-Aside 패턴을 도입하여 채팅 및 워크플로 응답 속도를 1ms로 극한 최적화.
- **Phase 22**: Chat Performance & Context Optimization. 프론트엔드 DOM 렌더링 방어막(최근 50개) 및 백엔드 LLM 토큰 낭비 방지(Truncation) 로직 구현.
- **Phase 23**: Admin Dashboard Statistics. 백엔드 DB 통계 파이프라인 연동하여 프론트엔드에 실시간 앱/대화 개수 표기.
- **Phase 24**: 전면적인 문서 총정리 및 아키텍처 스펙 동기화.
- **Phase 25**: 에이전트 코어 실전화. LLM 계층 재작성(async/스트리밍/native tool calling/Anthropic 어댑터),
  SuperAgent 3-phase(Planner→Researcher→Reporter) 재구현, 실제 검색/크롤 도구 연결, MCP 연결 재사용.
- **Phase 26**: 프로덕션 보안 하드닝. netguard SSRF 가드(DNS resolve 기반 사설 IP 차단),
  샌드박스 폴백 opt-in 전환 + argv 실행 + 타임아웃 강제 kill, dummy_key 제거(fail fast).
- **Phase 27**: 장시간 작업 인프라. 백그라운드 잡(DB 영속화 + 재접속 가능한 SSE),
  워크플로 실행 관측성(노드별 NodeRun 로그 + workflow_runs 이력 API).
- **Phase 28**: OSS 갭 해소. browser_agent(LLM 브라우저 제어 루프), deep_research(HITL 계획 검토 포함),
  workflow condition/http 노드, slides 테마/템플릿/PDF 출력.
- **Phase 29**: B2B 멀티 클라이언트 체계. 배포 프로파일(브랜딩/기능 플래그) + `GET /api/v1/profile`,
  **Control Plane 서비스**(배포 등록·라이선스 발급/차단·하트비트 상태 감시·관리 대시보드),
  프로파일 hot-reload(재배포 없는 원격 설정 변경), 사용량 미터링(작업/토큰 집계 → 하트비트 보고).

## 진행 중 / 다음 작업
- 백그라운드 잡(`/api/v1/jobs`) 경로 사용량 미터링 연결 (현재는 `/api/v1/tasks` 경로만 집계).
- 고객사 마스터 슬라이드 템플릿(`zeropark_engines/templates/{theme}.pptx`) 실제 CI 적용 파이프라인.
- Neo4j 기반 Knowledge Graph (GraphRAG) 엔진의 자체 내장 또는 MCP를 통한 고도화 통합.
- 고객 피드백에 따른 UI/UX 개선 및 프론트엔드 추가 기능(무한 스크롤 고도화 등) 구현.

## 블로커 / 주요 리스크
- **로컬 Docker 환경 의존성**: 현재 백엔드의 핵심 보안 기능(Sandbox)과 DB/Cache (Qdrant, Redis)가 모두 Docker에 의존합니다. 개발 PC에 Docker Desktop이 구동되어 있지 않으면 시스템 기동 자체가 불가한 리스크가 발견되었습니다.
- **해결책**: 오프라인 및 Non-Docker 환경을 위한 Fallback Mock 모드를 프론트엔드/백엔드 곳곳에 방어 로직으로 이중화해야 합니다.
