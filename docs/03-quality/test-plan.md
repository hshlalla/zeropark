---
doc_type: test_plan
project_id: zeropark
status: in_progress
updated_at: 2026-06-09
---

# 테스트 계획 (Zeropark)

## 1. 범위

- **core 스파인**: registry(등록/조회/capability 필터), router(plan/select/resolve/선호도), config(env 매핑).
- **engines(네이티브)**: 각 엔진의 capability 핸들러 — 정규화 출력(TaskResult/Artifact/SourceRef) 검증.
- **gateway**: /health·/route·/tasks·/search·/crawl·/slides 와이어링(E2E, 네트워크 없이).

## 2. 실행

```bash
pip install -e packages/zeropark-core -e packages/zeropark-engines -e services/gateway
pytest            # 루트 pyproject의 testpaths + --import-mode=importlib
```

현재: **24 passed**.

## 3. 엔진 테스트 원칙 (외부 의존 없이)

- crawl: `params.html` 주입으로 네트워크 없이 HTML→markdown 검증.
- slides: tmp 디렉터리에 실제 `.pptx` 생성 후 python-pptx로 슬라이드 수 검증.
- search: 백엔드 미설정 시 미등록 → /search 503. (실호출은 통합 테스트로 분리.)
- 네트워크가 필요한 케이스(실제 fetch/LLM)는 `@pytest.mark.integration`으로 분리(기본 제외).

## 4. capability별 게이트(추가 예정)

| capability | 단위 | 통합 |
|---|---|---|
| crawl | html→md, 링크/메타 | 실제 URL fetch |
| slides | outline→pptx 구조 | LLM outline 생성 |
| research | 인용 정규화 | search+crawl+LLM 파이프라인 |
| browse | 액션 직렬화 | Playwright 실제 세션 |

## 5. 품질 기준

- 정규화 출력 스키마 준수, 에러 매핑(503/502/400) 일관성, 회귀(인용 유효성·산출물 export) 평가 하니스(Phase 6).
