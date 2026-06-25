# Filler Skills

## ★★ 최상위 원칙 — 표·차트·텍스트 박스 모두 채우기

값이 들어가야 하는 위치는 **세 종류 모두**다. Filler는 이 셋을 전부 채워야 한다:

| 종류 | 채우기 방법 | 현재 상태 |
|------|------------|-----------|
| **표(table) 셀** | `write_cell()` (SlideMapping 기반) | ✅ |
| **텍스트 박스(text)** | `write_text_shape()` (SlideMapping 기반) | ✅ |
| **차트(chart)** | `core/chart_fill.py` → `chart.replace_data()` | ✅ (전용 모듈) |

- 차트는 SlideMapping이 아니라 **전용 모듈 `core/chart_fill.py`**가 채운다 (Filler가 표·텍스트 채운 뒤 호출).
- `chart_fill`은 정답지 차트 구조를 직접 읽어 raw_data로 채운다(`series.values` 직접 수정 금지 — `chart.replace_data` 사용).
- 차트는 두 종류 모두 처리 대상: **(1) 월별 시계열**(막대=월) **(2) 카테고리별 막대**(막대=플랫폼/intent/채널 등).
- 데이터 주도: 데이터에 있는 월/카테고리만 채우고 나머지는 보고한다.

---

## Skill 4: Fill Completeness & Integrity Guard (★ 최우선)

### 목적
Filler가 PPT를 저장하기 전, 채우기 완성도와 잔여 placeholder를 검증해 무결성을 보장한다.

---

### Sub-Skill 4-A: Fill Completeness Check

**입력**: SlideMapping.targets 수 (mapping_count), 실제 성공 셀 수 (filled_count)

**규칙**
```
if filled_count != mapping_count → FAIL
```

**허용 기준**: `filled_count == mapping_count` (100%)

**FAIL 시 출력 형식**:
```
[Filler] ⚠ [Skill 4] FAIL Fill Completeness: filled=X / required=Y (미채우기 Z개)
```

**Never**:
- 미채우기 셀이 있는데 "완료"로 처리하지 말 것
- 경고만 남기고 조용히 넘기지 말 것

---

### Sub-Skill 4-B: Placeholder Preservation

**규칙**: 텍스트 도형 쓰기 시 KPI 값만 교체하고, 접두 텍스트는 반드시 보존한다.

**보존 대상 접두 텍스트** (예시):
- `"MoM"`, `"vs. Global"`, `"vs. Co.A"`, `"▲"`, `"▼"`

**교체 대상 placeholder 패턴**:
```regex
[+-]?0\.0%p     # ±0.0%p (MoM)
0\.0%(?!p)      # 0.0%   (pct)
0\.0[KB]        # 0.0K, 0.0B
x0\.0           # x0.0 (ratio)
x1\.0           # x1.0 (ratio neutral)
```

**예시 (올바른 동작)**:
```
입력 도형 텍스트: "MoM ▲ 0.0%p"
계산 값:         "+2.3%p"
출력 도형 텍스트: "MoM ▲ +2.3%p"   ← "MoM ▲ " 보존, 숫자만 교체
```

```
입력 도형 텍스트: "vs. Global\n+0.0%p"   (<a:br> 구분)
계산 값:         "+1.5%p"
출력 도형 텍스트: "vs. Global\n+1.5%p"  ← 접두 보존
```

**Never**:
- 전체 텍스트 프레임을 지우고 값만 쓰지 말 것
- "MoM", "vs. Global" 등 레이블 텍스트가 사라지는 코드를 작성하지 말 것

---

### Sub-Skill 4-C: Unfilled Scan (저장 전 최종 검증)

**시점**: `prs.save(out_path)` 호출 **직전**

**탐색 대상**: 전체 PPT의 모든 텍스트 도형 + 테이블 셀

**탐색 패턴**:
```regex
[+-]?0\.0%p     # MoM placeholder
0\.0%(?!p)      # pct placeholder
0\.0[KB]        # K/B scale placeholder
x0\.0           # ratio placeholder
x1\.0           # ratio neutral placeholder
```

**FAIL 기준**: 잔여 placeholder 1개 이상

**FAIL 시 출력**:
```
[Filler] ⚠ [Skill 4] FAIL Unfilled Scan: N개 잔여 placeholder 발견
  slide=0 shape='직사각형 5': '+0.0%p'
  ...
```

**Pass 시 출력**:
```
[Filler] [Skill 4] ✓ Unfilled Scan: 잔여 placeholder 없음
```

**Never**:
- ~~차트의 0.0 값은 탐색 대상에서 제외~~ → **차트도 반드시 탐색 포함** (Skill 5 참조)
- FAIL이어도 PPT는 반드시 저장 (FAIL = 경고, not abort)
- 잔여 수를 조용히 누락하지 말 것

---

## Skill 5: Chart & Table Fill (★ 필수 — "미구현" 상태 종료)

### 목적
PPT 내 모든 **차트**(bar, line, pie 등)와 **표(table)**의 숫자값을 계산된 KPI로 반드시 채운다.
차트나 표를 비워두거나 0/placeholder 상태로 저장하면 무조건 FAIL이다.

---

### Sub-Skill 5-A: 표(Table) 채우기

**규칙**
- SlideMapping.targets 중 `shape_type="table"` 인 모든 항목은 `write_cell`로 채운다.
- 셀에 `0.0%`, `0.0K`, `+0.0%p`, `x0.0` 등의 placeholder가 남아있으면 FAIL.
- header 행(row=0 또는 row=1)도 동적 값이면 반드시 채운다.

**채우기 순서**: SlideMapping 순서대로 순회 → 행 우선(row asc) → 열 우선(col asc)

**FAIL 출력**:
```
[Filler] ⚠ [Skill 5-A] FAIL Table Unfilled: slide=N shape=M [row,col] key='...'
```

---

### Sub-Skill 5-B: 차트(Chart) 채우기

**규칙**
- SlideMapping.targets 중 `shape_type="chart"` 인 모든 항목은 `chart.replace_data(chart_data)`로 채운다.
- 차트 계열(series) 값이 모두 0이거나 None이면 FAIL.
- categories(X축 레이블)도 반드시 실제 날짜/카테고리명으로 채운다.

**python-pptx 채우기 패턴**:
```python
from pptx.chart.data import ChartData

chart_data = ChartData()
chart_data.categories = ["Jan", "Feb", "Mar"]   # 실제 기간/카테고리
chart_data.add_series("Samsung BV", (12.3, 13.1, 14.5))  # 실제 KPI 시계열
chart_data.add_series("Apple BV",   (18.2, 17.9, 18.6))

shape = find_shape(slide, shape_num)   # 차트 도형 찾기
shape.chart.replace_data(chart_data)
```

**format_hint 해석**:
- `"chart:BAR:series0"` → BarChart, 첫 번째 계열
- `"chart:LINE:series1"` → LineChart, 두 번째 계열
- 여러 계열이 있으면 SlideMapping 순서대로 `add_series` 호출

**FAIL 출력**:
```
[Filler] ⚠ [Skill 5-B] FAIL Chart Unfilled: slide=N shape=M (계열 값 비어있음)
```

**Never**:
- 차트 도형을 발견했는데 SlideMapping에 없다고 건너뛰지 말 것 → 즉시 경고 출력
- `chart.replace_data` 없이 series.values만 직접 수정하지 말 것 (OXml 깨짐 위험)
- 차트 채우기를 "향후 구현"으로 미루지 말 것

---

### Sub-Skill 5-C: 채우기 후 차트 검증

**시점**: `prs.save(out_path)` 호출 **직전**

**탐색 대상**: 전체 PPT의 모든 차트 도형

**FAIL 기준**:
1. 차트 계열 값이 모두 동일한 값(0, None, placeholder)
2. categories가 비어있거나 `["Category 1", "Category 2", ...]` 기본값 유지

**Pass 시 출력**:
```
[Filler] [Skill 5] ✓ Chart Fill: N개 차트 모두 채워짐
```
