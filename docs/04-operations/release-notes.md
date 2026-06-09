---
doc_type: release_notes
project_id: zeropark
status: in_progress
updated_at: 2026-06-09
---

# 릴리즈 노트 (Zeropark)

## v0.1.0 — 네이티브 기반 (Unreleased)

방향: OSS를 API로 호출하지 않고 **네이티브 단일 프레임워크**로 구현. OSS는 설계 참고만.

### Added
- core 스파인: capabilities, models, Provider(ABC), registry, router, config.
- 네이티브 엔진: crawl(httpx+markdownify), slides(python-pptx), search(옵션 백엔드).
- gateway: 코어/엔진에 위임하는 FastAPI(/health·/route·/tasks·/search·/crawl·/slides).
- 문서: architecture / dependency-isolation / capability-roadmap / decision-log 정비.

### Changed
- (피벗) HTTP 어댑터 방식 폐기 → 네이티브 엔진. `zeropark-adapters` 제거(→`zeropark-engines`).
- 기준 문서를 GitLab 대시보드 템플릿 → Zeropark 제품으로 재정렬.

### Notes
- 라이선스: Dify/SearXNG 소스 비차용. MIT/Apache 차용 시 `THIRD_PARTY_NOTICES.md` 표기.
- 테스트 24 passed.

### Next
- LLM client 추상 → research/super_agent → browse/sheets → workflow/RAG (capability-roadmap.md).
