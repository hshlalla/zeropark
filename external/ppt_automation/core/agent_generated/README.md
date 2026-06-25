# core/agent_generated/

**에이전트가 템플릿/데이터를 "보고 저작(著作)"하는 모든 것.**
다른 템플릿이 들어오면 이 폴더의 내용은 (이상적으로) 그 템플릿에 맞게 새로 만들어져야 한다.
범용 엔진은 `core/predefined/` 에 있으며 템플릿이 바뀌어도 그대로 재사용된다.

## 1. 템플릿 특화 로직 모듈 (버전 관리 대상 `.py`)

에이전트가 "어떻게 계산하고 어디에 넣을지"를 코드로 표현한 것. 현재는 손으로 작성한
스캐폴드이며, 새 템플릿에서는 이 자리에 에이전트가 생성한 코드가 들어간다.

| 파일 | 역할 | 템플릿 특화 지점 |
|------|------|------------------|
| `metric_resolver.py`    | value_key → MetricId 파싱 | entity 집합(samsung/apple), 키 네이밍 규약 |
| `formula_critic.py`     | 후보 공식 타당성 심사 | 도메인 규칙(samsung↔galaxy 등) |
| `formula_fit.py`        | 정답지 값 역산으로 식 적합 | 세그먼트 컬럼명(`_SEGMENT_DIMS`) |
| `chart_fill.py`         | 차트 계열/축 채우기 | 차원 컬럼명(`_DIM_COLS`) |
| `formatters.py`         | KPI 값 → 표시 문자열 | 단위·표기 규약(`%`, `%p`, `K`, `x1.10`, ÷1000) |
| `formula_synthesizer.py`| 후보 공식 생성 | fmt→scale 매핑(pct→×100, kval→÷1000), `_DENOM_RE` 컬럼명 |

## 2. 런타임 산출물 (자동 생성, git 미추적)

에이전트가 매 실행에서 분석해 만들어내는 결정. `.gitignore` 처리됨.

| 폴더 | 내용 | 생성 노드 |
|------|------|-----------|
| `mappings/`    | `mapping_*.json` — **어디에 뭘 넣을지** (SlideMapping) | Reader |
| `plans/`       | `formula_plan_*.json` — **도출된 계산식** (FormulaPlan/KeySpec) | Planner |
| `formulas/`    | `formulas_*.py` — **계산식 고정 코드** (편집·단독실행 가능) | Calculator |
| `calculators/` | `kpi_calculator_*.py` — LLM fallback 코드 (FormulaPlan 없을 때만) | Calculator |

### `formulas/` — 계산식을 코드로 고정 (B 구조)

Planner가 도출한 KeySpec을 `core/predefined/formula_codegen.py`가 **결정론적으로 `.py`로
직렬화**해 `formulas_{template+answerkey hash}.py`로 고정한다. Calculator는 매번 다시 도출하지
않고 이 파일을 import해 실행한다.

- **한 번 도출 → 코드로 고정 → 이후 재사용.** raw_data만 바뀌는 월간 재실행은 같은 식 코드로 새 값 계산.
- 파일은 **사람이 편집·단독 실행** 가능: `python formulas_xxx.py <data_dir> <cur_date> <prv_date>`
- 재생성은 파일이 없거나 Planner 자아 진화(retry_feedback) 때만. 그 외엔 기존 코드 존중·재사용.

> 기계적 캐시(`scans/` 원본 덤프, `memory.db` 공유메모리)는 에이전트의 "결정"이 아니므로
> 이 폴더가 아닌 프로젝트 루트 `generated/` 에 둔다.
