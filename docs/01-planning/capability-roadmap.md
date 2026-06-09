---
doc_type: capability_roadmap
project_id: zeropark
status: in_progress
updated_at: 2026-06-09
---

# Capability 로드맵 & 갭 분석

참고 OSS(deer-flow, dify, crawl4ai, presenton, browser-use 등)의 기능 표면을 조사해, 현재
네이티브 구현과의 격차와 앞으로 만들 기능을 정리한다. **모두 네이티브로 재구현**하며 OSS는 참고만.

## 0. 한눈에

| capability | 현재 | 목표 수준(참고 OSS) | 우선순위 |
|---|---|---|---|
| crawl | ✅ v1 (정적 HTML→md) | Crawl4AI급(JS·추출·딥크롤) | P1 |
| search | ◻ 스텁 | 멀티 백엔드 메타서치 | P1 |
| research | ⏳ | DeerFlow급 딥리서치 | P1 |
| super_agent | ⏳ | DeerFlow급 플래너+서브에이전트 | P2 |
| slides | ✅ v1 (outline→pptx) | Presenton급(LLM생성·템플릿·차트) | P2 |
| sheets | ⏳ | 스키마·데이터·수식·차트·xlsx | P2 |
| dashboard | ⏳ | 데이터→차트→공유 페이지 | P3 |
| browse | ⏳ | browser-use급 LLM 브라우저 | P3 |
| workflow/RAG | ⏳ | Dify급 RAG·툴·워크플로 | P3 |

## 1. 횡단 인프라 (여러 capability 공통 — 최우선)

이게 없으면 research/slides/browse/workflow를 제대로 못 만든다. **먼저 구축.**

| 인프라 | 역할 | 참고 OSS | 라이브러리(네이티브) | Phase |
|---|---|---|---|---|
| **LLM client 추상** | 멀티프로바이더(OpenAI/Anthropic/Gemini/Azure/Bedrock/Ollama/로컬) 통일 호출 | 전부 | httpx + 공식 SDK, OpenAI 호환 | 2 |
| **Tool/Skill 레지스트리** | 에이전트가 쓰는 도구(search/crawl/python/file/http) 등록·호출 | DeerFlow, browser-use, Dify(50+ tools) | 자체 | 2 |
| **MCP 클라이언트** | 외부 MCP 도구 소비 | DeerFlow, browser-use | mcp SDK | 3 |
| **Memory + Vector store** | 단기/장기 기억, 임베딩 검색 | DeerFlow, Dify(RAG) | pgvector/Qdrant 클라이언트 | 2 |
| **Sandbox(코드 실행)** | 격리된 Python REPL/툴 실행 | DeerFlow sandboxes | 컨테이너/subprocess 격리 | 3 |
| **Artifact store** | 산출물 영속·버전·공유 링크 | (제품) | Postgres + S3 호환 | 5 |
| **Observability/LLMOps** | 토큰·비용·지연·트레이스·주석 | browser-use tokens, Dify LLMOps | 자체 + OTel | 5 |
| **Streaming(SSE)** | RunEvent 실시간 스트림 | 전부 | FastAPI SSE | 3 |
| **Vision/멀티모달** | 스크린샷→LLM | browse/crawl | Playwright + 멀티모달 LLM | 3 |
| **MCP 서버(노출)** | Zeropark capability를 MCP로 외부 제공 | Presenton MCP | mcp SDK | 6 |

## 2. capability별 갭

### crawl — 현재 v1, 목표 Crawl4AI급
참고 보유: JS 렌더링, **fit-markdown(노이즈 제거)**, BM25/콘텐츠 필터, **LLM 추출**, CSS/XPath 스키마 추출,
청킹, **딥크롤(BFS/DFS·링크 추적)**, 스크린샷/PDF, 세션·프록시·쿠키·훅, 미디어/메타데이터, 캐싱.
계획: ① Playwright 렌더 변형 ② fit-markdown 필터 ③ 스키마/LLM 추출 ④ 딥크롤 ⑤ 캐시·세션.

### search — 현재 스텁, 목표 멀티 백엔드
참고 보유(DeerFlow): Tavily/Brave/DuckDuckGo/Arxiv 등 + 결과 통합.
계획: 커머디티 백엔드 어댑터(Brave/Bing/Tavily) + Arxiv + dedup·랭킹. (SearXNG는 AGPL이라 비차용.)

### research — 미구현, 목표 DeerFlow급 딥리서치
참고 보유: 플래너→리서치/작성 서브에이전트, 배경조사, **인용 포함 리포트**, 휴먼인더루프 계획 편집,
podcast/PPT/prose 출력.
계획: search+crawl+LLM 오케스트레이션 → 인용 정규화(SourceRef) → 리포트 템플릿. (LLM client·tool 레지스트리 선행.)

### super_agent — 미구현, 목표 DeerFlow급 하니스
참고 보유: 장기계획, 서브에이전트, **메모리**, **샌드박스**, 스킬, MCP 툴.
계획: 플래너 + 서브에이전트 그래프(자체 경량) + tool/skill 레지스트리 + memory + sandbox + MCP.

### slides — 현재 v1(렌더만), 목표 Presenton급
참고 보유: **프롬프트/문서→덱 LLM 생성**, 템플릿/테마(HTML+Tailwind), 기존 PPTX→템플릿, **차트·이미지**, PDF export, 팩트체크, MCP 서버.
계획: ① LLM outline 생성 ② 템플릿/테마 ③ 차트(matplotlib)·이미지(생성/스톡) ④ PDF export ⑤ 팩트체크 패스.

### sheets — 미구현 (Genspark AI Sheets 참고)
계획: 스키마 설계(LLM) → 데이터 수집(search/crawl) → 수식 생성 → 차트 → **xlsx(openpyxl)**.

### dashboard — 미구현
계획: 데이터 인제스트 → 차트 스펙 → 인터랙티브 HTML 페이지 → 새로고침/공유.

### browse — 미구현, 목표 browser-use급
참고 보유: LLM 에이전트 루프, **DOM 직렬화/추출**, 액션 컨트롤러(click/type/scroll/navigate/upload),
멀티탭, **비전/스크린샷**, 민감정보 처리, 커스텀 액션, MCP, 파일시스템, 토큰/비용.
계획: Playwright + DOM 직렬화 + 액션셋 + LLM 루프 + 비전 + allowlist/rate-limit/audit.

### workflow / RAG — 미구현, 목표 Dify급
참고 보유: 비주얼 워크플로, **RAG(PDF/PPT/docx 인제스트→청킹→임베딩→검색→리랭크)**,
에이전트(function-calling/ReAct)+50+ 툴, 모델 관리, 프롬프트 IDE, LLMOps, BaaS API.
계획: RAG 파이프라인 + 툴/에이전트 프레임 + 노드 그래프 워크플로 + 모델 관리 + 관측성. (Dify 소스 비차용, 독립 구현.)

## 3. Phase 매핑(개정)

| Phase | 추가/확장 항목 |
|---|---|
| 2 (현재) | 코어 스파인 ✅, crawl v1 ✅, slides v1 ✅ + **LLM client 추상**, **tool/skill 레지스트리**, **memory/vector**, search v1 |
| 3 | research v1, browse v1(Playwright), crawl v2(JS·추출·딥크롤), SSE 스트리밍, MCP 클라이언트, Web Shell |
| 4 | super_agent(샌드박스), slides v2(LLM·템플릿·차트), sheets v1, dashboard v1, workflow/RAG v1 |
| 5 | artifact store·버전·공유, observability/LLMOps |
| 6 | 보안(SSRF·prompt-injection·allowlist), 라이선스 최종, 평가 하니스, 패키징, MCP 서버 노출 |

## 4. 참고 OSS ↔ capability 매핑

| OSS | 라이선스 | 참고 대상 capability |
|---|---|---|
| DeerFlow (MIT) | 차용 가능 | research, super_agent, search, tool/skill, memory, sandbox |
| Crawl4AI (Apache+attr) | 차용 가능 | crawl |
| Presenton (Apache) | 차용 가능 | slides |
| browser-use (MIT) | 차용 가능 | browse |
| Dify (제한) | **비차용** | workflow, RAG, 모델관리, LLMOps (독립 구현) |
| SearXNG (AGPL) | **비차용** | search (커머디티 API로 대체) |
| OpenManus/Coze/UI-TARS | 확인 필요 | agent/GUI 참고(선택) |
