# 역할별 정보 범위 (Selective Information Disclosure)

"숨기기"가 아니라 **각 역할에 필요한 정보만 전달**한다 — 컨텍스트 절약 + 판단 정확도.
역할이 받는 입력을 아래 범위로 제한한다. (필요 이상으로 PPT 전체 문맥을 넘기지 말 것)

---

## Metric Resolver
**받는 것**: `value_key` + 주변 PPT 문맥(슬라이드 제목, 표 헤더, "(2-X)" 주석)
**안 받음**: 데이터 값, 다른 슬라이드
**출력**: `MetricId(metric_family, entity, country, period, comparison, extras)`

## Formula Synthesizer
**받는 것**: `MetricId` + 데이터셋 스키마(컬럼명만)
**안 받음**: PPT 문맥, 정답지 값
**출력**: 후보 공식 목록 `[{df_key, num, denom, scale}, ...]`

## Formula Validator
**받는 것**: 후보 목록 + raw_data + 참조값(정답지/전월/타국가 target)
**안 받음**: PPT 문맥
**출력**: 후보별 (상대오차, 참조수)

## Formula Critic  ← 더 많이 본다 (의미 판단용)
**받는 것**: 후보 공식들 + **계산 결과** + **evidence**(채택 후보의 계산값·오차, 대안 후보들)
**이유**: "숫자는 맞지만 의미가 이상한" 공식을 거르려면 계산결과+후보비교가 필요
**출력**: (통과 여부, 사유)

## Calculator  ← 최소만 본다 (계산만)
**받는 것 (이것만)**:
```json
{
  "metric_id": "bv_samsung_us_cur",
  "dataset": "bv",
  "columns": ["galaxy_mention", "denominator"],
  "filters": {"company": "Samsung", "country": "US"},
  "period": "cur",
  "scale": 100.0
}
```
**절대 안 받음**: PPT 전체 문맥, 정답지, 슬라이드 텍스트, 다른 KPI
**이유**: 계산엔 KeySpec만 있으면 충분 → 컨텍스트 대폭 절약. (현재 엔진이 이미 KeySpec만 받음 ✓)

## Manager
**받는 것**: 각 게이트 산출물의 **요약 + confidence**(전체 원본 아님)
**출력**: 통과/재시도/human review 라우팅

---

## 원칙 요약
| 역할 | 정보량 | 핵심 |
|------|--------|------|
| Resolver | 문맥 일부 | 분류에 필요한 문맥만 |
| Synthesizer | 스키마 | 컬럼명만 |
| Validator | 데이터+참조 | 계산·비교만 |
| **Critic** | **많음** | 후보+계산+evidence (의미 판단) |
| **Calculator** | **최소** | KeySpec만 (PPT 문맥 ✗) |
| Manager | 요약+confidence | 라우팅 판단만 |
