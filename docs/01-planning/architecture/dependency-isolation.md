---
doc_type: architecture
project_id: zeropark
status: in_progress
updated_at: 2026-06-09
---

# 통합·의존성·라이선스 전략 (네이티브 단일 프레임워크)

## 1. 왜 OSS 엔진을 번들하지 않는가

OSS 엔진을 그대로 가져와 한 프로젝트에 통합하면 의존성이 정면충돌한다(실측):

| | DeerFlow | Dify | Presenton | Crawl4AI | browser-use |
|---|---|---|---|---|---|
| Python | `>=3.12` | `~=3.12.0` | 3.11 검증 | `>=3.10` | `>=3.11,<4.0` |
| FastAPI | `>=0.115` | `==0.136.0` | — | — | `==0.128.0` |

- FastAPI: Dify `0.136.0` vs browser-use `0.128.0` → 한 환경 공존 불가.
- Python: Dify 3.12 전용 vs Crawl4AI/Presenton 3.11.

→ 그래서 **엔진을 의존성으로 들이지 않는다.** 대신 기능을 **네이티브로 재구현**한다.
엔진을 import 하지 않으므로 위 충돌은 애초에 발생하지 않는다.

## 2. 채택 전략: 네이티브 구현 + OSS는 참고만

```
zeropark-core / zeropark-engines / gateway  ──  하나의 깔끔한 의존성 세트
   └─ 사용 라이브러리(퍼미시브): httpx, markdownify, python-pptx, openpyxl, Playwright, LLM client

external/ (OSS)  ──  설계 참고용. import X, 실행 X, 배포에 미포함.
```

- 제품 코드는 `external/*`를 **절대 import 하지 않는다.**
- 각 capability는 검증된 경량 라이브러리로 직접 구현한다.

## 3. capability별 네이티브 라이브러리 매핑

| capability | 라이브러리(퍼미시브) | 참고 OSS |
|---|---|---|
| crawl | httpx + markdownify (+ Playwright) | Crawl4AI (Apache-2.0) |
| slides | python-pptx | Presenton (Apache-2.0) |
| sheets | openpyxl | — |
| search | 커머디티 검색 API 클라이언트 | SearXNG는 **불가**(아래) |
| browse | Playwright | browser-use (MIT) |
| research / agent | 자체 경량 오케스트레이터 + LLM client | DeerFlow (MIT) |
| workflow / RAG | 자체 그래프 + 벡터스토어(pgvector/Qdrant) | Dify는 **불가**(아래) |

## 4. "참고" vs "코드 차용" — 라이선스 경계 (판매 필수)

| OSS | 라이선스 | 소스 차용 | 방침 |
|---|---|---|---|
| DeerFlow, browser-use | MIT | 가능(attribution) | 차용 시 NOTICES 표기 |
| Presenton, Crawl4AI | Apache-2.0(+attr) | 가능(attribution/NOTICE) | 차용 시 NOTICES 표기 |
| **Dify** | 별도 상용/브랜딩 조건 | **금지** | 기능만 독립 재구현 |
| **SearXNG** | AGPL-3.0(네트워크 카피레프트) | **금지** | 커머디티 검색 API로 대체 |

원칙: **모든 OSS는 설계 참고가 기본.** 코드를 실제로 복붙하는 건 MIT/Apache에 한해 attribution과 함께만.
Dify/SearXNG는 한 줄도 가져오지 않는다(제품 전체가 오염됨).

## 5. 엔진 소스(참고본) 관리

- `external/`는 `.gitignore`. 빌드/배포에 포함되지 않음(참고용 로컬 체크아웃).
- 참고한 OSS·버전·차용 범위는 `THIRD_PARTY_NOTICES.md`와 각 엔진의 `reference` 필드에 기록.
- 차용이 전혀 없고 독립 구현이면 NOTICES에 "design reference only"로 표기.
