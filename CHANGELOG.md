0.2.0
- `zeropark-core` `router.py`에 `ppt_agent` ModePlan 추가 — 프론트엔드 `/modes` API 및 앱 생성 UI에 자동 노출
- `.gitignore`에 `plans/`, `debug_hang.py` 추가, `qdrant_data/` 트래킹 해제
- `external/ppt_automation` git 트래킹 추가 (런타임 캐시·출력물·로그 제외)

0.1.0
- `zeropark-core` Capability 열거형에 `PPT_AGENT` 항목 추가
- `zeropark-engines`에 LangGraph 기반 PPT 자동화 엔진(`PptAutoEngine`) 통합
- `zeropark-engines` ppt 선택적 의존성 그룹(langchain-core, langgraph 등) 추가

0.0.1
- 초기 프로젝트 문서 템플릿, GitLab Issue/MR 템플릿, AI 에이전트 작업 지침 추가