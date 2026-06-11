# OSS Source Map

This file tracks the public software we used as **design references only** (no code imported, no
service embedded), how each maps to the product, and the native module that replaced it.

| ID | Source | Role | License posture | Use decision | Native replacement (status) |
| --- | --- | --- | --- | --- | --- |
| `deer-flow` | https://github.com/bytedance/deer-flow | Super-agent harness: planning, sub-agents, citations | MIT | Design reference only | ✅ `super_agent.py` (Planner→Researcher→Reporter), `deep_research.py` (섹션별 검색·인용·HITL) |
| `dify` | https://github.com/langgenius/dify | Workflow builder, RAG, observability | Modified Apache-2.0 with extra conditions | **Source 차용 금지** — design reference only | ✅ `workflow.py` (DAG, condition/http 노드, NodeRun 관측성), `rag.py`, workflow run 이력 API |
| `openmanus` | https://github.com/FoundationAgents/OpenManus | General AI agent reference | MIT | Design reference only | ✅ `super_agent.py` 도구 루프에 흡수 |
| `presenton` | https://github.com/presenton/presenton | AI presentation generation, PPTX/PDF export | Apache-2.0 | Design reference only | ✅ `slides.py` (테마/템플릿/노트/이미지 + LibreOffice PDF) |
| `crawl4ai` | https://github.com/unclecode/crawl4ai | LLM-ready crawling, markdown conversion | Apache-2.0 + attribution | Design reference only | ✅ `crawl.py` (httpx+markdownify, SSRF 가드), `LLMCrawlEngine` (구조화 추출) |
| `searxng` | https://github.com/searxng/searxng | Self-hosted metasearch | AGPL-3.0 | **소스/서비스 미사용** — 의도적 대체 | ✅ `search.py` commodity search API 클라이언트 (Brave/Bing/Tavily 등) |
| `browser-use` | https://github.com/browser-use/browser-use | Browser automation for agents | MIT | Design reference only | ✅ `browser_agent.py` (LLM이 요소 인덱스 기반 click/type/navigate 반복) |
| `coze-studio` | https://github.com/coze-dev/coze-studio | Visual agent/workflow builder alternative | Apache-2.0 | Optional reference (미사용) | — |
| `ui-tars-desktop` | https://github.com/bytedance/UI-TARS-desktop | Multimodal GUI/computer-use stack | Apache-2.0 | Optional reference (미사용) | — |

## Functional Mapping

| Genspark-like capability | Design reference | Native implementation | Remaining gap |
| --- | --- | --- | --- |
| One prompt to many outputs | DeerFlow | Router(mode→capability→engine) + `/api/v1/tasks(/stream)` SSE + Artifact 모델 | — |
| Deep research with sources | DeerFlow + Crawl4AI | `deep_research.py`: 계획→섹션별 검색/크롤→[n] 인용 보고서, HITL 계획 검토 | source trust scoring, 보고서 템플릿 다양화 |
| Slides | Presenton | `slides.py`: 테마 3종+오버라이드, 고객사 마스터 템플릿(.pptx), PDF 출력 | 고객사 CI 템플릿 제작 파이프라인, deck 뷰어 UX |
| Sheets | Python data tooling | `sheets.py` (openpyxl) + LLM 생성 | 수식/차트 검증 루프 |
| Web/browser actions | browser-use | `browser_agent.py` + netguard 차단 + 방문 URL 감사로그(sources) | 도메인 allowlist 정책, 세션 재사용 |
| RAG and workflow apps | Dify | `rag.py`(Qdrant) + `workflow.py` + 실행 이력 API + React Flow UI | 워크플로 import/export, 노드 팔레트 확장 |
| Long-running jobs | — | `/api/v1/jobs`: DB 영속화 + 백그라운드 실행 + 재접속 SSE | 잡 경로 사용량 미터링 |
| Fleet management (B2B) | — | `services/control-plane`: 라이선스/하트비트/프로파일 hot-reload/사용량 대시보드 | 사용량 시계열 이력, 알림(offline 감지) |

## Commercial Launch Checklist

- Confirm every license and NOTICE file from pinned commits.
- Do not remove Dify frontend branding unless allowed by license/commercial agreement.
- Decide whether SearXNG is internal-only, unmodified, or replaced with a permissive search API adapter.
- Add Crawl4AI attribution in product credits and docs if used.
- Keep each external OSS repo pinned by commit/tag for reproducible builds.
- Track modifications to third-party source separately from product code.

