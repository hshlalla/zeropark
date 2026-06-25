# MX GEO Monitoring Report 자동화

Samsung MX GEO 모니터링 리포트 PPT를 원시 데이터에서 자동으로 생성하는 LangGraph 멀티 에이전트 파이프라인입니다.

## 빠른 시작

```bash
# 가상환경 활성화
source .venv/bin/activate

# 기본 빌드 (최신 월 자동 감지)
python build_report.py

# 특정 월 지정 (형식 자유: 월 숫자 / YYYY-MM / YYYY-MM-DD 모두 허용)
python build_report.py --month 4
python build_report.py --month 2026-04
python build_report.py --month 2026-04-26

# 캐시 무시하고 LLM 재생성 (템플릿·정답지 교체 후 사용)
python build_report.py --regenerate
```

## 프로젝트 구조

```
.
├── build_report.py          # 빌드 CLI
├── run.sh                   # 가상환경 활성화 + build_report.py 래퍼
├── requirements.txt
│
├── agents/                  # 멀티 에이전트 패키지
│   ├── graph.py             # LangGraph StateGraph (파이프라인 오케스트레이터)
│   ├── state.py             # AgentState TypedDict
│   ├── models.py            # Pydantic 스키마 (SlideMapping, KeySpec 등)
│   ├── utils.py             # 해시 유틸 (combined_hash, GENERATED_DIR)
│   │
│   ├── nodes/               # 에이전트 노드
│   │   ├── data_analyzer.py   # ① Excel → parquet 캐시 + 날짜 감지
│   │   ├── reader.py          # ② LLM → SlideMapping (셀 좌표 + KPI 키)
│   │   ├── calculator.py      # ③ LLM → KeySpecMapping → kpi_engine 계산
│   │   ├── filler.py          # ④ SlideMapping + CalculationResult → PPT 채우기 (결정론적)
│   │   └── verifier.py        # ⑤ SlideMapping.targets 셀 대조 + 라우팅
│   │
│   └── tools/               # 공통 유틸
│       ├── pptx_scanner.py    # PPT 도형 인벤토리 (shape_id, z_order, position, group 포함)
│       ├── kpi_engine.py      # 고정 집계 엔진: sum(value_col)/sum(denom_col)*scale
│       ├── formatters.py      # 숫자 → 표시 문자열 순수 함수 (fmt_pct, fmt_mom 등)
│       ├── ranking.py         # 도메인 경쟁식 순위 (_top_domains_prev)
│       └── excel_reader.py    # Excel 스키마 분석 (calamine 엔진)
│
├── raw_data/                # 원시 Excel 데이터 (2-1-1 ~ 2-4)
├── template/                # PPT 빈 템플릿 (*_base_template*.pptx)
├── answer_key/              # 정답지 PPT (검증용, 선택)
├── output/                  # 생성된 리포트
├── generated/               # LLM 캐시 (mapping_*.json, key_specs_*.json)
├── .data_cache/             # parquet 캐시 (bv/rv/rs/rd/rdp/st.parquet)
└── tools/regression/        # 회귀 테스트
```

## 에이전트 파이프라인

```
raw_data/ (Excel)
      │
      ▼
[① DataAnalyzer]   Excel → parquet 캐시, 날짜 감지, --month 정규화
      │  data_schema, data_cache_dir, target_month (YYYY-MM-DD)
      ▼
[② Reader]         LLM → SlideMapping (슬라이드·도형·셀 좌표 + value_key)
      │             캐시: generated/mapping_{template+answer_key 해시}.json
      ▼
[③ Calculator]     LLM → KeySpecMapping (집계 명세) → kpi_engine 계산
      │             캐시: generated/key_specs_{hash}.json
      ▼
[④ Filler]         SlideMapping + CalculationResult → PPT 셀 채우기 (결정론적)
      │
      ▼
[⑤ Verifier]       SlideMapping.targets 셀만 대조 → 통과 or 재시도 라우팅
      │
      ▼
   output/filled_YYYYMMDD.pptx
```

## 캐시 전략

| 캐시 | 키 | 무효화 조건 |
|---|---|---|
| parquet (`.data_cache/{raw_dir_hash}/`) | raw_data_dir 절대경로 MD5 | 소스 Excel mtime > parquet mtime |
| SlideMapping (`generated/mapping_*.json`) | template + answer_key MD5 | 둘 중 하나 변경 시 |
| KeySpecMapping (`generated/key_specs_*.json`) | template + answer_key + parquet mtime MD5 | 세 가지 중 하나 변경 시 (raw 데이터 포함) |

`--regenerate` 플래그를 쓰면 현재 템플릿+정답지의 LLM 캐시 두 파일을 삭제하고 재생성합니다.

## 환경 변수

`.env` 파일에 다음 키를 설정하세요:

```env
Score_Claude_API_KEY=sk-ant-...   # Anthropic API 키
```

## 데이터 소스

| 파일 접두사 | 내용 |
|---|---|
| `2-1-1` | Reference Share (RS) |
| `2-1-2` | Reference Domain (RD) |
| `2-1-3` | Reference Domain % (RDP) |
| `2-2` | Reference Visibility (RV) |
| `2-3` | Brand Visibility (BV) |
| `2-4` | Brand Sentiment (ST) |

## 회귀 테스트

```bash
# 빠른 테스트 (raw 데이터 불필요)
python -m unittest discover -s tools/regression -t .

# 골든 KPI 테스트 (parquet 캐시 필요)
RUN_GOLDEN=1 python -m unittest discover -s tools/regression -t .
```

## 의존성 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
