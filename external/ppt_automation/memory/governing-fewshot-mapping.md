---
name: governing-fewshot-mapping
description: How the governing Excel maps to prompts/fewshot.py few-shot slots (non-obvious: Excel deck layout ≠ report slides)
metadata:
  type: project
---

거버닝 엑셀(`governing_message/*.xlsx`, 시트 `MSG Text`)을 `geo_report/insights/prompts/fewshot.py` few-shot 으로 옮길 때의 매핑 규칙.

**핵심 함정:** 엑셀의 `Page` 컬럼은 리포트 슬라이드 번호가 **아니다**. 엑셀은 더 큰(60p) 원본 덱 레이아웃이라 Page 가 직접 안 맞는다. 매핑은 `Section`(리포트 구성) + `Data`(주요 지표) 기준으로 해야 한다.

- 리포트 슬라이드↔섹션/지표 정의는 [config/slide_map.py] (`SLIDE`, `COUNTRY_SLIDE_START=14`, `insight_section`).
- few-shot 라우팅 우선순위: `BY_SLIDE`(page=idx+1) > `BY_METRIC`/`BY_COUNTRY` > `BY_SECTION` > 거버닝 폴백. 슬3 은 `{"top","bp"}` 슬롯.
- 성과(7~13) 지표: 슬7 Brand Visibility · 슬8 Sentiment Share · 슬9 Reference Share · 슬10·11 Reference Visibility(Owned, 동일) · 슬12·13 Reference Visibility(External, 동일).
- 국가(15~27)=`COUNTRY_ORDER` 순서 US,UK,IN,AE,AU,FR,ES,DE,IT,BR,ID,KR,JP. 26-03 사이클에서 엑셀 Page 33~45 가 이 순서대로 국가별 1페이지(헤드라인+세부3)로 깔끔히 대응(JP 는 +59 보강).
- 가장 최근 2개 사이클만 사용(26-03 primary + 26-01). few-shot 은 상위 6개만 쓰므로 최신 채널 분류·톤 우선.

주의: 26-01 엑셀의 BR 페이지(p56) 한 행이 "FR MX 노출도…"로 시작하는 원본 오타가 있음 — fewshot.py 에 그대로 옮겨둠(거버닝 충실 반영). 향후 정정 시 수정.
