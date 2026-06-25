# Reader Skills

## ★★ 최상위 원칙 — 값이 들어가는 곳은 모두 채워진다 (역할 분담)

원래 숫자(값)가 들어가는 위치는 표·텍스트·차트 세 종류이며, **전부 채워져야 한다.**
다만 **채우는 담당(파이프라인)이 나뉜다**:

| 종류 | 담당 | Reader가 할 일 |
|------|------|----------------|
| **표(table) 셀** | Reader → Planner → Filler | `shape_type="table"`로 매핑 ✅ |
| **텍스트 박스(text)** | Reader → Planner → Filler | `shape_type="text"`로 매핑 ✅ |
| **차트(chart) 본체** | **전용 모듈 `core/chart_fill.py`** | **매핑하지 않음** (chart_fill이 정답지 차트를 직접 읽어 채움) |

- **Reader는 표·텍스트만 매핑한다.** 차트 본체(`shape_type="chart"`)는 만들지 않는다 — contract와 동일.
  (차트는 월별 시계열/카테고리별 막대라 셀 SlideMapping으로 표현이 부적합 → 전용 모듈이 처리)
- **차트 옆 숫자 텍스트 라벨**(MoM 등)은 차트가 아니라 **text 도형**이므로 `shape_type="text"`로 반드시 매핑한다.
- 즉 "차트도 채워진다"는 원칙은 유지되며, 그 구현 담당이 Reader가 아니라 chart_fill일 뿐이다.

---

## Skill 3: 헤더 + 정답지 주석으로 "무슨 값 / 어느 데이터" 파악 (★ 핵심)

표가 안 채워지는 주원인은 "이 셀이 무슨 지표이고 어느 데이터에서 계산하는지"를 몰라서다.
**정답지는 그 답을 두 가지로 명시한다 — 반드시 읽어라.**

### (1) 표 헤더 → 무슨 지표/구조인가
표의 헤더 행·열은 각 셀이 무슨 값인지 알려준다:
```
[표 헤더 예 — slide14]
  r0: 'Brand Visibility'        ← 지표명 (metric_family = bv)
  r1: '80.4%'   | 'MoM -0.9%p'  ← 현재값 | MoM
  r2: 'vs. Global +3.6%p' | 'vs. Co.A +2.5%p'  ← 비교값(diff)
```
- 헤더 텍스트("Brand Visibility", "Reference Visibility", "Sentiment", "Owned", "Dotcom", 플랫폼명 등)로 **metric_family와 세그먼트**를 판단한다.
- 행/열 위치로 **현재값 / MoM / vs.Global / vs.Co.A** 역할을 구분한다.

### (2) 정답지의 "(2-X)" 주석 → 어느 데이터 파일에서 계산하는가 (★★)
정답지에는 `AX 필요 영역 (2-X)` 형태의 주석이 있고, 이 `2-X`가 **데이터 파일(df_key)**을 직접 가리킨다:

| 정답지 주석 | 데이터 파일 | df_key | 지표 |
|------------|------------|--------|------|
| `(2-1)` / `(2-1-1~3)` | 2-1-1/2/3 | rs / rd / rdp | Reference Sales/Data |
| `(2-2)` | 2-2 | **rv** | Reference Visibility |
| `(2-3)` | 2-3 | **bv** | Brand Visibility |
| `(2-4)` | 2-4 | **st** | Sentiment |

→ 이 주석을 읽으면 **df_key를 추측하지 않고 확정**할 수 있다. (key 접두사보다 이 주석이 우선)
   `(2-3)` 주변 표/차트 → bv.parquet, `(2-2)` → rv.parquet, `(2-4)` → st.parquet.

### 적용
- 셀의 metric_family/df_key를 정할 때: **① 가까운 "(2-X)" 주석 → df_key 확정**, ② 헤더 텍스트 → 지표/세그먼트, ③ 행·열 위치 → 현재/MoM/vs 역할.
- 이 신호로 value_key·context를 더 정확히 생성하면 Planner가 식을 더 많이 만든다.

### Never
- 헤더·주석을 무시하고 셀 위치만으로 추측하지 말 것.
- "(2-X)" 주석이 있는데 다른 데이터셋으로 계산하지 말 것.

---

## Skill 2: KPI Discovery Completeness (★ 최우선)

### 목적
PPT 내 모든 숫자 Placeholder를 반드시 찾아 매핑한다.
누락된 placeholder가 있으면 FAIL.

### 반드시 탐지해야 하는 Placeholder

**Table Cell**
- `0.0%`
- `0.0K`
- `+0.0%p`
- `x0.0`

**Text Shape** (차트 위/옆 레이블 포함)
- `MoM +0.0%p`
- `vs. Global +0.0%p`
- `vs. Co.A +0.0%p`
- `+0.0%p` 또는 `-0.0%p` 단독

**Chart Series** (★ 필수 — 미구현 아님)
- 차트 도형(`has_chart=True`)이 있는 슬라이드는 반드시 `shape_type="chart"`로 매핑해야 한다.
- 각 계열(series)의 값(values)이 placeholder(0, 0.0, None 등)이면 KPI key를 부여한다.
- `format_hint`에 차트 타입(`BAR`, `LINE`, `PIE` 등)과 series 인덱스를 명시한다.
  예) `"chart:BAR:series0"`, `"chart:LINE:series1"`

### Placeholder Detection Rule
다음 패턴이 포함된 셀/도형은 KPI 후보다:
```
0\.0%
0\.0K
0\.0B
\+0\.0%p
\-0\.0%p
x0\.0
x1\.0
```

### Mapping Completeness Check (Reader 종료 전 반드시 수행)
```
total_numeric_placeholders  = 소형 테이블(≤5행) 셀 + 텍스트 도형 + 차트 도형 합계
mapped_placeholders         = SlideMapping에 포함된 개수
coverage                    = mapped / total
```
**조건: coverage < 95% → FAIL**

**차트 미매핑 = FAIL**: 슬라이드에 차트 도형이 존재하는데 SlideMapping에 포함되지 않으면 즉시 FAIL.

### Duplicate KPI Detection (★ 절대 규칙)
동일 KPI가 여러 슬라이드에 반복될 수 있다.
예) Brand Visibility → Summary Slide, Country Slide, Trend Slide

이 경우 모든 위치에 반드시 **동일한 value_key** 사용:
```json
{
  "key": "bv_samsung_global_cur",
  "targets": [
    {"slide_idx": 3, "shape_num": 91, "row": 0, "col": 0},
    {"slide_idx": 10, "shape_num": 91, "row": 0, "col": 0},
    {"slide_idx": 18, "shape_num": 91, "row": 0, "col": 0}
  ]
}
```
**절대 별도 KPI 생성 금지**: `bv_samsung_global_cur_summary`, `bv_samsung_global_cur_country` 등으로 분리하지 말 것.

### Never
- 숫자 placeholder가 있는 셀/도형을 건너뛰지 말 것
- 동일 KPI를 다른 이름의 key로 중복 생성하지 말 것
- coverage 95% 미만을 허용하지 말 것
