"""formula_fit.py — 정답지(answer key) 값을 target으로 KeySpec(식)을 역산.

아이디어:
  "이 셀의 정답이 80.4%다" → raw_data에서 80.4%를 재현하는
  (분자 컬럼 / 분모 컬럼 / 세그먼트 필터) 조합을 탐색해 식을 확정한다.

탐색이 성공하면 KeySpec, 실패하면 None(=정의 불가 → 보고 대상).

도메인 하드코딩 없음:
  - 분자 후보 = 데이터의 숫자 컬럼을, key 토큰과 컬럼명 겹침으로 우선순위화
  - 분모 후보 = 이름에 denom/denominator/total 포함 컬럼 (+ 분모 없음)
  - 세그먼트 = 범주형 차원(platform/intent/generic_branded/channel) 0~1개 필터
  - company/country 필터 = key 토큰에서 추론 (데이터 실제 값에 매칭)
"""
from __future__ import annotations

import re

import pandas as pd
from agents.models import KeySpec
from domain.config import TOLERANCE_MOM, TOLERANCE_OTHER, TOLERANCE_PCT

# 세그먼트 후보로 쓸 범주형 차원 (있으면 0~1개를 필터로 시도)
_SEGMENT_DIMS = ["platform", "intent_lv1", "generic_branded", "channel", "sentiment"]
# 분모로 쓸 만한 컬럼명 패턴
_DENOM_RE = re.compile(r"denom|denominator|total|base", re.I)


def _toks(s: str) -> set[str]:
    return set(t for t in re.split(r"[_\s]+", s.lower()) if t)


def parse_period(key: str) -> str:
    for p in ("vs_coa", "vs_global", "mom", "ratio", "prv", "cur"):
        if key.endswith("_" + p) or ("_" + p + "_") in key:
            return {"vs_coa": "diff", "vs_global": "diff"}.get(p, p)
    return "cur"


def parse_entity_filters(key: str, df: pd.DataFrame) -> dict[str, str]:
    """key 토큰에서 company/country 필터를 데이터 실제 값으로 추론."""
    filters: dict[str, str] = {}
    toks = _toks(key)
    if "company" in df.columns:
        cvals = {str(v).lower(): str(v) for v in df["company"].dropna().unique()}
        for t in toks:
            if t in cvals:
                filters["company"] = cvals[t]
                break
    if "country" in df.columns:
        cvals = {str(v).lower(): str(v) for v in df["country"].dropna().unique()}
        for t in toks:
            if t in cvals:
                filters["country"] = cvals[t]
                break
    return filters


def _numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _candidate_numerators(
    key: str, numeric: list[str], denom_cols: list[str], top: int = 8
) -> list[str]:
    """key 토큰과 컬럼명 겹침으로 분자 후보 우선순위화 (denom 제외)."""
    cands = [c for c in numeric if c not in denom_cols]
    ktoks = _toks(key)
    cands.sort(key=lambda c: -len(ktoks & _toks(c)))
    return cands[:top]


def _tol_for(fmt: str) -> float:
    if fmt == "pct":
        return TOLERANCE_PCT
    if fmt == "mom":
        return TOLERANCE_MOM
    return TOLERANCE_OTHER


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """날짜를 1회만 정규화('_dnorm')해 fit 반복 비용을 제거. 데이터셋당 1회 호출."""
    df = df.copy()
    if "date" in df.columns:
        df["_dnorm"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def _sum(sub, col):
    return float(pd.to_numeric(sub[col], errors="coerce").sum()) if col in sub.columns else None


def _agg_sub(sub, value_col, denom_col):
    """이미 (날짜·엔티티·세그먼트) 필터된 sub에서 집계."""
    if value_col not in sub.columns or len(sub) == 0:
        return None
    num = _sum(sub, value_col)
    if denom_col:
        den = _sum(sub, denom_col)
        return num / den if den else None
    return num


def fit_key(key: str, target: float, fmt: str, df_key: str, df: pd.DataFrame,
            cur: str, prv: str, try_segments: bool = True,
            tol_override: float | None = None) -> KeySpec | None:
    """정답지 target을 재현하는 KeySpec을 탐색. 실패 시 None.

    성능: 엔티티(company/country)·날짜 슬라이스를 1회만 수행하고,
    분자/분모/세그먼트 조합은 작은 부분집합 위에서 평가한다.
    df는 prepare()로 '_dnorm'이 추가돼 있어야 빠르다.
    """
    period = parse_period(key)
    if period == "diff":
        return None  # vs_coa/vs_global(diff)은 base 정의 필요 → 여기선 미지원(보고 대상)

    base_filters = parse_entity_filters(key, df)
    numeric = _numeric_cols(df)
    denom_cols = [c for c in df.columns if _DENOM_RE.search(c)]
    numerators = _candidate_numerators(key, numeric, denom_cols)
    denom_options = [""] + denom_cols

    if fmt in ("pct", "mom"):
        scale_options = [100.0]
    elif fmt == "kval":
        scale_options = [0.001]
    elif fmt == "ratio":
        scale_options = [1.0]
    else:
        scale_options = [1.0, 100.0, 0.001]
    tol = tol_override if tol_override is not None else _tol_for(fmt)

    # ── 엔티티 슬라이스 1회 → cur/prv 부분집합 ──────────────────────────
    ent = df
    for col, val in base_filters.items():
        if col in ent.columns:
            ent = ent[ent[col].astype(str) == str(val)]
    dcol = "_dnorm" if "_dnorm" in ent.columns else ("date" if "date" in ent.columns else None)
    cur_e = ent[ent[dcol] == cur] if dcol else ent
    prv_e = ent[ent[dcol] == prv] if dcol else ent

    def _val(cs, ps, num, denom, scale):
        if period in ("cur", "prv"):
            a = _agg_sub(cs if period == "cur" else ps, num, denom)
            return a * scale if a is not None else None
        if period == "mom":
            a = _agg_sub(cs, num, denom)
            b = _agg_sub(ps, num, denom)
            return (a - b) * scale if a is not None and b is not None else None
        if period == "ratio":
            a = _agg_sub(cs, num, denom)
            b = _agg_sub(ps, num, denom)
            return (a / b) * scale if a is not None and b not in (None, 0) else None
        return None

    def _best_over(seg_options):
        best_spec = None
        best_err = float("inf")
        for seg in seg_options:
            cs, ps = cur_e, prv_e
            for sc, sv in seg.items():
                if sc in cs.columns:
                    cs = cs[cs[sc].astype(str) == str(sv)]
                    ps = ps[ps[sc].astype(str) == str(sv)]
            if len(cs) == 0:
                continue
            for num in numerators:
                for denom in denom_options:
                    for scale in scale_options:
                        val = _val(cs, ps, num, denom, scale)
                        if val is None:
                            continue
                        err = abs(val - target)
                        if err < best_err:
                            best_err = err
                            best_spec = KeySpec(
                                key=key, df_key=df_key, value_col=num, denom_col=denom,
                                filters={**base_filters, **seg}, period=period, scale=scale,
                                note=f"fit→{round(val, 2)} (target {target}, err {round(err, 2)})",
                            )
        return best_spec, best_err

    # 1) 세그먼트 없는 단순 식 우선 (오차 최소 후보 선택 → 우연 일치 방지)
    spec, err = _best_over([{}])
    if spec is not None and err <= tol:
        return spec

    # 2) 단순 식이 안 맞으면 세그먼트(depth-1) 탐색
    if try_segments:
        seg_options = []
        for dim in _SEGMENT_DIMS:
            if dim in df.columns:
                for v in df[dim].dropna().unique():
                    seg_options.append({dim: str(v)})
        if seg_options:
            spec2, err2 = _best_over(seg_options)
            if spec2 is not None and err2 <= tol:
                return spec2
    return None


# ── 정답지 target 읽기 ────────────────────────────────────────────────────────

_NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def parse_value(s: str) -> float | None:
    """정답지 셀 문자열을 숫자로 파싱. 'vs.'/개행 접두 제거.

    '80.4%' → 80.4, '+1.2%p' → 1.2, '25.9K' → 25.9, 'vs. Global\\x0b+3.6%' → 3.6
    """
    if not s:
        return None
    s = str(s).split("\x0b")[-1].split("\n")[-1]
    s = s.replace("K", "").replace("%p", "").replace("%", "").replace(",", "").strip()
    m = _NUM_RE.search(s)
    try:
        return float(m.group()) if m else None
    except ValueError:
        return None


def build_targets(answer_slides: list[dict], mapping_targets: list[dict]) -> dict[str, dict]:
    """매핑된 셀들의 정답지 값을 key별로 모아 대표 target을 만든다.

    같은 key가 값이 다른 여러 셀에 매핑된 경우(매핑 불일치) → 최빈값을 target으로,
    distinct 개수를 함께 기록(불일치 진단용).

    반환: {key: {"target": float, "fmt": str, "n_cells": int, "n_distinct": int, "values": [...]}}
    """
    # (slide_idx, shape_num, row, col) → 값,  (slide_idx, shape_num) → 텍스트
    cell_val: dict[tuple, str] = {}
    text_val: dict[tuple, str] = {}
    for sl in answer_slides:
        idx = sl["slide_idx"]
        for sh in sl["shapes"]:
            num = sh.get("num")
            if sh.get("type") == "table" and sh.get("grid"):
                for r, row in enumerate(sh["grid"]):
                    for c, v in enumerate(row):
                        cell_val[(idx, num, r, c)] = str(v or "")
            elif sh.get("type") == "text" and sh.get("text"):
                text_val[(idx, num)] = sh["text"]

    from collections import Counter, defaultdict
    by_key: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for t in mapping_targets:
        key = t["value_key"]
        st = t.get("shape_type", "table")
        if st == "text":
            raw = text_val.get((t["slide_idx"], t["shape_num"]), "")
        else:
            raw = cell_val.get((t["slide_idx"], t["shape_num"], t["row"], t["col"]), "")
        v = parse_value(raw)
        if v is not None:
            by_key[key].append((round(v, 2), t.get("format_type", "pct")))

    out: dict[str, dict] = {}
    for key, vals in by_key.items():
        nums = [v for v, _ in vals]
        cnt = Counter(nums)
        target = cnt.most_common(1)[0][0]
        fmt = vals[0][1]
        out[key] = {
            "target": target, "fmt": fmt,
            "n_cells": len(nums), "n_distinct": len(cnt),
            "values": sorted(cnt.keys()),
        }
    return out
