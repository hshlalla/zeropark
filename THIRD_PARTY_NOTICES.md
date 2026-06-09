# Third-Party Notices

Zeropark는 OSS 엔진을 **런타임에 사용하지 않습니다.** 기능은 퍼미시브 라이브러리로 네이티브
구현하며, OSS는 **설계 참고**로만 활용합니다. (전략: `docs/01-planning/architecture/dependency-isolation.md`)

## 1. 런타임 라이브러리 (네이티브 구현에 실제 사용)

| 라이브러리 | 용도 | 라이선스 |
|---|---|---|
| httpx | HTTP 클라이언트 | BSD-3 |
| markdownify | HTML→Markdown (crawl) | MIT |
| python-pptx | PPTX 생성 (slides) | MIT |
| pydantic / pydantic-settings | 모델·설정 | MIT |
| fastapi / uvicorn | 게이트웨이 | MIT / BSD |
| (계획) openpyxl, Playwright | sheets, browse | MIT, Apache-2.0 |

## 2. 설계 참고 OSS (소스 차용 시 attribution 필요)

| OSS | 라이선스 | 차용 가능 | 비고 |
|---|---|---|---|
| ByteDance DeerFlow | MIT | 예(attribution) | research/agent 참고 |
| Crawl4AI | Apache-2.0 + attribution | 예(attribution) | crawl 참고. 차용 시 아래 문구 포함 |
| Presenton | Apache-2.0 | 예(NOTICE) | slides 참고 |
| browser-use | MIT | 예(attribution) | browse 참고 |
| Dify | Dify OSS License(상용 조건) | **아니오** | 독립 재구현만 |
| SearXNG | AGPL-3.0 | **아니오** | 커머디티 검색 API로 대체 |

### Crawl4AI attribution (소스/설계를 차용해 배포할 경우 포함)

> This product includes software developed by UncleCode (https://x.com/unclecode)
> as part of the Crawl4AI project (https://github.com/unclecode/crawl4ai).

## 3. 정책

- Dify/SearXNG 소스는 한 줄도 복사하지 않는다(제품 라이선스 오염 방지).
- MIT/Apache 소스를 차용하면 이 파일에 출처·범위를 기록한다.
- 차용 없이 독립 구현한 엔진은 `reference` 필드에 "design reference only"로 표기한다.
