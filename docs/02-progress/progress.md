---
doc_type: progress
project_id: zeropark
status: in_progress
progress: 25
updated_at: 2026-06-09
---

# 개발 진행 현황 (Zeropark)

## 전체 진행률: `25%` — Phase 2(코어/엔진 스파인) 진행 중

## Phase 상태

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | 리포 기반·문서 | ✅ 완료 |
| 1 | OSS 스모크(참고용 검증) | ✅ 완료 |
| 2 | 코어 스파인 + 네이티브 엔진 | 🔵 진행 |
| 3 | Web Shell | ⏳ |
| 4 | 나머지 capability 네이티브 구현 | ⏳ |
| 5 | 아티팩트 저장·공유 | ⏳ |
| 6 | 보안·라이선스·상용화 | ⏳ |

## 완료된 작업 (2026-06-09)

- `zeropark-core`: capabilities, models, Provider(ABC, cap_ 디스패치), registry, router, config.
- **LLM Client 추상화 및 Tool 레지스트리 초안** (`zeropark_core/llm.py`, `zeropark_core/tools.py`) 추가 완료.
- **Research / Super Agent 기능 (경량 오케스트레이터)** (`zeropark_engines/research.py`) 구현 완료.
- **Slides 콘텐츠 자동 생성 (LLM 연동)** (`LLMSlidesEngine`) 구현 완료.
- **Sheets 콘텐츠 자동 생성 (openpyxl & LLM 연동)** (`LLMSheetsEngine`) 구현 완료.
- **Browse 웹 자동화 엔진 (Playwright 연동)** (`PlaywrightBrowseEngine`) 구현 완료.
- **Web Shell 프론트엔드 UI (React+Vite)** (`packages/zeropark-web`) 구현 완료.
- `zeropark-engines`: NativeEngine + **crawl(httpx+markdownify) 구현**, **slides(python-pptx) 구현**, search(옵션) + loader.
- `services/gateway`: 코어/엔진에 위임하는 얇은 FastAPI(13 routes).
- 방향 피벗: 엔진 API 호출/격리 서비스 폐기 → 네이티브 단일 프레임워크. `zeropark-adapters`(HTTP) 폐기.
- 문서 재정렬: 기준 문서를 GitLab 대시보드 → Zeropark로. 아키텍처/의존성/결정기록 갱신.
- 테스트: **24 passed** (core registry/router/config, engines crawl/slides/loader, gateway catalog/app).

## 로드맵

참고 OSS 갭 분석과 전체 capability 계획: [capability-roadmap.md](../01-planning/capability-roadmap.md).
횡단 인프라(LLM client·tool 레지스트리·memory·sandbox·observability)부터 선행.

## 진행 중 / 다음

- [x] `external/` 참고본 커밋 핀 기록.

## 블로커

`docs/02-progress/blockers.md` 참고.
