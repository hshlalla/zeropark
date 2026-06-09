---
doc_type: blockers
project_id: zeropark
status: active
updated_at: 2026-06-09
---

# 블로커 및 리스크 (Zeropark)

## 활성 항목

| 항목 | 내용 | 영향 | 대응 |
|---|---|---|---|
| 범위 | 5개 엔진 기능을 네이티브로 "유사" 재구현 = 큰 작업 | 일정 | capability별 점진 구현(crawl·slides 완료), 우선순위화 |
| LLM 의존 | research/agent/slide-content는 LLM 필요 | 기능 | provider-agnostic LLM client 추상 먼저 |
| 검색 | SearXNG(AGPL) 비차용 → 커머디티 검색 API 필요 | search | 클라이언트가 API 키 구성(Brave/Bing 등) |
| 라이선스 | Dify/SearXNG 소스 차용 금지 | 판매 | 독립 재구현, NOTICES 관리 |
| 재현성 | `external/` 참고본 커밋 미고정 | 추적성 | NOTICES에 커밋/차용 범위 기록 |
| 버전관리 | 커밋 0개, 브랜치 `master`(규칙은 main) | 거버넌스 | 초기 커밋 + main 정정 |

## 해결됨

| 항목 | 해결 |
|---|---|
| 의존성 충돌(FastAPI/Python) | 엔진을 import 하지 않는 네이티브 구현으로 원천 제거 |
| 기준 문서 split-brain | docs를 Zeropark 제품으로 재정렬 |
