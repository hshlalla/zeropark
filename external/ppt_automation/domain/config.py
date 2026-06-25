"""domain/config.py — 프로젝트 도메인 설정 파일.

새 템플릿이나 데이터셋을 적용할 때는 이 파일만 수정하세요.
agents/ 와 core/ 의 나머지 코드는 이 파일에서 도메인 정보를 읽어갑니다.

------------------------------------------------------------------
수정 필요 항목:
  1. FILE_KEYS        — raw_data/ 파일명 접두사 ↔ 내부 키 매핑
  2. DATE_PRIORITY    — 기준월 자동 감지에 사용할 파일 우선순위
  3. CATEGORICAL_COLUMNS — 스키마 분석 시 유니크값을 추출할 컬럼 목록
  4. TOLERANCE_*      — 정답지 검증 허용 오차 (단위별)
------------------------------------------------------------------
"""
from __future__ import annotations

# ── 데이터 파일 키 매핑 ────────────────────────────────────────────────────────
# raw_data/ 폴더에서 파일을 찾는 접두사와 파이프라인 내부 단축 키의 매핑
# key   : 파이프라인 내부에서 사용하는 식별자 (parquet 파일명이 됨)
# value : raw_data/ 내 파일명 접두사 (예: "2-3"이면 "2-3.xlsx" 를 탐색)
FILE_KEYS: dict[str, str] = {
    "rs":  "2-1-1",   # Reference Sales
    "rd":  "2-1-2",   # Reference Data
    "rdp": "2-1-3",   # Reference Data Plus
    "rv":  "2-2",     # Reference Visibility
    "bv":  "2-3",     # Brand Visibility
    "st":  "2-4",     # Sentiment
}

# ── 날짜 자동 감지 우선순위 ────────────────────────────────────────────────────
# FILE_KEYS 의 key 순서 — 앞에 있는 파일부터 "date" 컬럼을 읽어 기준월 결정
# 해당 파일이 없으면 다음 파일로 넘어감
DATE_PRIORITY: list[str] = ["bv", "rv", "st", "rs", "rd", "rdp"]

# ── 스키마 분석: 범주형 컬럼 목록 ─────────────────────────────────────────────
# 이 컬럼들의 유니크값(최대 30개)을 추출해 LLM에게 데이터 구조를 알려줍니다.
# 새 데이터셋의 범주형 컬럼을 여기에 추가하세요.
CATEGORICAL_COLUMNS: list[str] = [
    "company",
    "country",
    "platform",
    "date",
    "channel",
    "generic_branded",
    "intent_lv1",
    "sentiment",
]

# ── 정답지 "(2-X)" 데이터 출처 주석 → 데이터셋(df_key) ────────────────────────
# 정답지의 "AX 필요 영역 (2-X)" 주석이 어느 데이터 파일에서 계산하라는지 직접 가리킨다.
# Reader/Resolver가 셀의 df_key를 추측 대신 이 주석으로 확정하는 데 사용.
# (2-1은 rs/rd/rdp가 모두 2-1-x라 후보 다수 → 헤더로 보조 판단)
ANNOTATION_TO_DATASET: dict[str, list[str]] = {
    "2-1":   ["rs", "rd", "rdp"],
    "2-1-1": ["rs"],
    "2-1-2": ["rd"],
    "2-1-3": ["rdp"],
    "2-2":   ["rv"],
    "2-3":   ["bv"],
    "2-4":   ["st"],
}


# ── 국가 코드 (value_key 파싱용) ──────────────────────────────────────────────
# Metric Resolver가 value_key에서 country 토큰을 식별하는 데 사용.
# 데이터의 country 컬럼 값과 일치시킨다.
KNOWN_COUNTRIES: list[str] = [
    "AE", "AU", "BR", "DE", "ES", "FR", "ID", "IN", "IT", "JP", "KR", "UK", "US",
]


# ── KPI 키 접두사 → 데이터셋(df_key) 매핑 ────────────────────────────────────
# Planner가 정답지 기반으로 식을 역산할 때, KPI 키 접두사로 어느 parquet을 쓸지 결정.
# 여기 없는 접두사(traffic/domain/topdomain/chart/sourcetype 등)는 자동 식 구성 대상이
# 아니며 "정의 불가"로 보고된다 (랭킹·파생·차트 등 단순 집계로 안 되는 지표).
METRIC_PREFIX_TO_DATASET: dict[str, str] = {
    "bv":        "bv",   # Brand Visibility
    "rv":        "rv",   # Reference Visibility
    "rs":        "rs",   # Reference Sales
    "sentiment": "st",   # Sentiment
    "st":        "st",
}

# ── 검증 허용 오차 ─────────────────────────────────────────────────────────────
# 정답지(answer_key)와 생성 PPT 값을 비교할 때 허용하는 오차 범위.
# 테스트 데이터와 프로덕션 데이터 간 분포 차이를 보정합니다.
TOLERANCE_PCT: float = 4.5    # "%" KPI (예: Brand Visibility 76.8%)
TOLERANCE_MOM: float = 3.0    # "%p" MoM 변화량 (예: +0.9%p)
TOLERANCE_OTHER: float = 0.40  # ratio, raw 등 기타 (예: x0.85)
