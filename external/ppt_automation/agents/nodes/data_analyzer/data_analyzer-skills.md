# DataAnalyzer Skills

## Skill 1: KPI Coverage Validation

### 목적
입력 데이터에 KPI 계산에 필요한 컬럼이 실제 존재하는지 검증한다.

### Rules
- parquet 생성 후 모든 컬럼 목록을 저장한다
- 컬럼명은 lowercase로 normalize한다
- DataFrame별 row count를 저장한다
- 빈 DataFrame 발견 시 warning을 생성한다
- Calculator 요청 컬럼이 존재하지 않으면 즉시 FAIL 처리한다

### Output
```json
{
  "dataset": "bv",
  "rows": 15324,
  "columns": ["date", "company", "country", "galaxy_mention", "denominator", ...]
}
```

### Never
- 존재하지 않는 컬럼명을 추정하지 말 것
- 빈 DataFrame을 정상 데이터로 처리하지 말 것

---

## Skill 2: KPI 값 출처 정의 (Value Source Definition) — ★ 누락 방지 핵심

### 왜 값이 누락되는가 (실측 진단)
값이 비는 것은 데이터가 없어서가 아니라 **"이 자리에 어떤 값이 들어가야 하는지에 대한 정의"가 없어서**다.

| 지표 | 일치율 | 원인 |
|------|--------|------|
| sentiment, bv, rs | 79~98% | 컬럼명이 직관적(`galaxy_mention`/`denominator`) → 정의 없이도 매핑됨 |
| **rv / rs** | 56% (434 누락) | 컬럼이 **84개**이고 이름이 난해(`Owned__Owned_Total__Owned_Total`, `Owned__Dotcom_Support_Total__...`) → 어느 컬럼이 분자/분모인지 **정의가 없으면 추론 불가** |
| **traffic** | 0% (34 누락) | `traffic`라는 **데이터셋이 아예 없음** → 어느 원천(rd/rdp 등)에서 어떻게 유도하는지 **정의 필요** |
| **domain / topdomain** | 0% (80 누락) | 단순 합산이 아니라 **도메인 랭킹 집계**(top-N) → 집계 로직 정의 필요 |
| **vs_coa** | 16% | 경쟁사 대비 **차이(diff)** → 기준(base) 필터 정의 필요 |
| **chart** | 0% (23 누락) | 차트 계열 값 채우기 로직 + 데이터 정의 필요 |

→ 결론: **난해한 컬럼·파생 지표·랭킹·비교 지표는 명시적 정의가 없으면 반드시 누락된다.**

### 핵심 원칙 — 어느 값이 들어갈지는 "에이전트가 정의"해야 한다
이 정의는 사람이 떠먹여 주는 것이 아니라 **DataAnalyzer(너)가 책임지고 정의**해야 한다.
템플릿에서 **원래 숫자(값)가 들어가는 모든 위치**를 하나도 빠짐없이 정의하라:

- **표(table) 셀** — 모든 수치 셀
- **차트(chart)** — 모든 계열·데이터포인트·축 값
- **텍스트 박스(text box)** — 안에 들어있는 모든 숫자(MoM 레이블 `▲ 0.0%p`, 요약 수치, vs 비교값 등)

"표만" 정의하고 차트나 텍스트 박스를 빠뜨리면 그 자리는 그대로 빈다.

### Rules — 각 숫자 위치마다 반드시 정의할 것
각 위치에 대해 다음을 모두 명시한다 (KeySpec과 동일 구조):
1. **데이터셋(df_key)** — 어느 parquet에서 가져오는가
2. **분자 컬럼(value_col)** / **분모 컬럼(denom_col)** — 84컬럼처럼 난해하면 각 컬럼의 의미까지 정의
3. **필터(filters)** — company/country/platform 등, 반드시 **데이터의 실제 값**(예: country=`KR`, 대문자)
4. **집계 방식** — 단순합 / 비율 / **랭킹(top-N)** / **차이(diff)**
5. **기간(period)** — cur / prv / mom / ratio / vs
6. **파생 지표** — 원천 데이터셋이 직접 없으면(traffic 등) **어느 데이터에서 어떻게 유도하는지** 정의

### Never
- 정의가 없다는 이유로 셀을 빈칸/placeholder로 남기지 말 것
  → 반드시 정의를 추가하거나, 정말 불가하면 **"계산 불가 사유"를 명시적으로 기록**할 것
- 표만 정의하고 **차트·텍스트 박스를 빠뜨리지 말 것**
- 난해한 컬럼(`Owned__...`)을 추측으로 매핑하지 말 것 → **도메인 의미를 정의로 확정**할 것
- "데이터 분포 차이"로 단정하고 넘어가지 말 것 → 누락은 대부분 **정의 누락**이다
