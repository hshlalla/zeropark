---
doc_type: product_requirements
project_id: zeropark_v2
status: drafting
updated_at: 2026-06-09
---

# Zeropark V2 Enterprise (B2B) 요구사항 정의서

## 1. 제품 목적
Zeropark V1은 로컬 호스트 기반에서 돌아가는 개념 증명(PoC) 및 MVP 수준의 개인용 AI 워크스페이스였습니다.
Zeropark V2는 이를 기반으로 **완전한 엔터프라이즈급(B2B) SaaS 플랫폼**으로 도약하는 것을 목표로 합니다. 
보안, 다중 사용자 관리, 강력한 외부 스킬 연동, 비주얼 워크플로우를 제공하여 글로벌 오픈소스(Dify, Langflow 등)와 경쟁합니다.

## 2. 타겟 사용자
- **사내 AI 인프라 관리자 (Admin)**: 사내 데이터를 연동하고 API 비용을 통제하며 임직원의 접근 권한을 제어.
- **AI 워크플로우 빌더 (Power User)**: 코딩 없이 UI 기반 드래그 앤 드롭으로 AI 파이프라인(리서치->시트->슬라이드)을 생성.
- **일반 비즈니스 유저 (End User)**: 빌더가 만들어 둔 AI 워크플로우와 챗봇을 일상 업무(보고서 작성, 검색)에 활용.

## 3. 핵심 요구사항 (V1 대비 신규 추가)

### 3.1. 보안 및 완전 격리 실행 (Docker Sandbox)
- 파이썬 샌드박스의 `exec()` 방식을 폐기하고, **Docker Container 기반의 격리 환경**을 구축.
- LLM이 작성한 악성 코드가 호스트 시스템에 영향을 주지 못하도록 리소스(CPU, 메모리, 네트워크 아웃바운드)를 제한.

### 3.2. 비주얼 워크플로우 (Visual Workflow Builder)
- React Flow 기반의 **노드 에디터 UI** 개발.
- 사용자는 브라우저에서 '입력 폼', 'LLM 사고', '외부 API 호출', '문서 청킹', '출력 생성' 등의 노드를 연결하여 자신만의 다중 에이전트를 시각적으로 조립.

### 3.3. IAM (Identity and Access Management) & RBAC
- **OAuth 2.0 / SAML 연동**: 사내 구글 워크스페이스, Microsoft Entra ID 등과 로그인 연동.
- **Role-Based Access Control (RBAC)**: 관리자, 편집자, 뷰어 등급에 따라 접근 가능한 메뉴 및 RAG 지식 베이스(Knowledge Base) 풀(Pool)을 분리.
- **Admin 페이지**: 조직 관리, 사용자 초대, LLM 토큰 사용량 및 청구 내역 모니터링.

### 3.4. 고도화된 Knowledge Base (RAG)
- **UI 기반 문서 관리**: 사용자가 UI에서 PDF, 워드 문서를 직접 업로드하고 파싱 상태를 모니터링.
- **고급 청킹(Chunking) 제어**: UI에서 Chunk 토큰 사이즈, Overlap 사이즈, 파싱 규칙(QA 추출 방식 등)을 사용자가 직접 조정 가능.
- **권한 기반 벡터 스토어**: 로그인된 계정 등급에 따라 검색 가능한 문서를 필터링.

### 3.5. 확장성 및 생태계 (Integrations)
- **MCP HTTP/SSE 서버 분리**: 기존 로컬 Stdio 방식을 넘어, 클라우드 환경에서 동작하는 원격 MCP 통신 지원.
- **Node.js Custom MCP 통합**: 무거운 하드코딩 없이 수천 가지 도구를 노드 1개로 무한 확장.
- **Skill 마켓플레이스**: 외부 서드파티(Third-party) 플러그인을 쉽게 설치하고 끄고 켤 수 있는 모듈 시스템.

### 3.6. 극한의 성능 최적화 (High Performance)
- **Redis Cache-Aside Pattern**: 대화 기록 및 워크플로 캐싱을 통해 수십만 건의 세션 트래픽에도 1ms 대의 응답 속도 보장.
- **Frontend DOM 보호**: 수만 턴의 대화가 쌓여도 브라우저가 버벅이지 않도록 최근 50개의 메시지만 렌더링.
- **Backend LLM 컨텍스트 방어**: 무의미한 과거 대화로 인한 LLM 토큰 낭비를 막기 위해 Context Truncation 로직 적용.

### 3.7. Admin 실시간 대시보드 (Dashboard Statistics)
- 데이터베이스(SQLite, Qdrant 등)와 연동되어 생성된 워크플로 수, 누적 대화 수 등을 관리자에게 실시간으로 브리핑하는 통계 파이프라인.
