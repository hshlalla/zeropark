"""formula_engine.py — KeySpec(FormulaPlan)을 결정론적으로 실행하는 계산 엔진.

LLM이 코드를 생성하지 않는다. Planner가 만든 구조화 명세(KeySpec)를 그대로 해석해
parquet 데이터에서 각 KPI를 계산한다.

장점:
- 토큰/타임아웃/샌드박스 무관 (키가 수천 개여도 동작)
- 완전 추적 가능: 값이 틀리면 '명세(KeySpec)'가 틀린 것 → Planner 자아 진화로 수정
- 도메인 무관: 컬럼명·필터값은 모두 KeySpec에서 오므로 엔진은 범용

KeySpec 의미:
  집계 = sum(value_col) / sum(denom_col)   (denom_col 없으면 단순 sum)
  period:
    cur   → cur_date 집계
    prv   → prv_date 집계
    mom   → cur 집계 − prv 집계
    ratio → cur 집계 ÷ prv 집계
    diff  → (filters, cur) 집계 − (base_filters, cur) 집계
  최종값 = 위 결과 × scale   (ratio는 보통 scale=1)
"""
from __future__ import annotations

import os
import pandas as pd

# 필터 값이 이들 중 하나이면 "전체"를 의미 → 해당 컬럼 필터를 적용하지 않는다.
_WILDCARD_FILTER_VALUES = {"", "global", "all", "전체", "total"}


def _norm_dates(series: pd.Series) -> pd.Series:
    """날짜 컬럼을 'YYYY-MM-DD' 문자열로 정규화 (datetime/문자열 혼용 대응)."""
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def _aggregate(
    df: pd.DataFrame,
    value_col: str,
    denom_col: str,
    filters: dict[str, str],
    exclude: dict[str, list[str]],
    date: str | None,
) -> float | None:
    """필터/날짜 적용 후 sum(value_col)/sum(denom_col) 또는 sum(value_col) 반환.

    컬럼 부재·빈 데이터·0 분모는 None 반환 (방어적).
    """
    sub = df

    # 날짜 필터
    if date and "date" in sub.columns:
        sub = sub[_norm_dates(sub["date"]) == date]

    # 포함 필터 (wildcard 값은 생략)
    for col, val in (filters or {}).items():
        if val is None:
            continue
        if str(val).strip().lower() in _WILDCARD_FILTER_VALUES:
            continue
        if col in sub.columns:
            sub = sub[sub[col].astype(str) == str(val)]

    # 제외 필터
    for col, vals in (exclude or {}).items():
        if col in sub.columns and vals:
            sub = sub[~sub[col].astype(str).isin([str(v) for v in vals])]

    if value_col not in sub.columns or len(sub) == 0:
        return None

    num = pd.to_numeric(sub[value_col], errors="coerce").sum()
    if denom_col:
        if denom_col not in sub.columns:
            return None
        den = pd.to_numeric(sub[denom_col], errors="coerce").sum()
        return float(num) / float(den) if den else None
    return float(num)


def compute_spec(spec, load, cur_date: str, prv_date: str) -> float | None:
    """단일 KeySpec을 계산. load(df_key) → DataFrame|None."""
    df = load(spec.df_key)
    if df is None:
        return None

    vc, dc = spec.value_col, spec.denom_col
    flt, exc = spec.filters, spec.exclude_values
    scale = spec.scale

    if spec.period in ("cur", "prv"):
        d = cur_date if spec.period == "cur" else prv_date
        v = _aggregate(df, vc, dc, flt, exc, d)
        return v * scale if v is not None else None

    if spec.period == "mom":
        a = _aggregate(df, vc, dc, flt, exc, cur_date)
        b = _aggregate(df, vc, dc, flt, exc, prv_date)
        return (a - b) * scale if a is not None and b is not None else None

    if spec.period == "ratio":
        a = _aggregate(df, vc, dc, flt, exc, cur_date)
        b = _aggregate(df, vc, dc, flt, exc, prv_date)
        return (a / b) * scale if a is not None and b not in (None, 0) else None

    if spec.period == "diff":
        a = _aggregate(df, vc, dc, flt, exc, cur_date)
        base_vc = spec.base_value_col or vc
        b = _aggregate(df, base_vc, dc, spec.base_filters, spec.base_exclude_values, cur_date)
        return (a - b) * scale if a is not None and b is not None else None

    return None


def execute_plan(plan, data_dir: str, cur_date: str, prv_date: str) -> dict[str, float | None]:
    """FormulaPlan(KeySpecMapping)의 모든 KeySpec을 실행해 {key: value|None} 반환.

    parquet은 df_key별로 1회만 로드(메모리 캐시). 한 spec 실패는 None으로 격리.
    """
    cache: dict[str, pd.DataFrame | None] = {}

    def load(df_key: str):
        if df_key not in cache:
            path = os.path.join(data_dir, f"{df_key}.parquet")
            try:
                cache[df_key] = pd.read_parquet(path) if os.path.exists(path) else None
            except Exception:
                cache[df_key] = None
        return cache[df_key]

    out: dict[str, float | None] = {}
    for spec in plan.specs:
        try:
            out[spec.key] = compute_spec(spec, load, cur_date, prv_date)
        except Exception:
            out[spec.key] = None
    return out
