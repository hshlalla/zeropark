"""chart_fill.py — 차트를 ChartTarget으로 구조화하고 raw_data로 채운다.

차트 종류:
  time      : 카테고리가 월(시계열). 각 막대 = 그 월의 메트릭.
  category  : 카테고리가 세그먼트 값(플랫폼/intent/채널 등). 각 막대 = 그 값으로 필터한 메트릭.

원칙(데이터 주도):
  - 정답지 차트 값을 target으로 (분자/분모/필터/scale) 식을 fit한다.
  - 데이터에 있는 월/카테고리만 채우고, 없으면 건너뛴다.
  - 식이 정답을 재현 못하면(타이트 오차 초과) 미해소로 보고한다.

표/텍스트와 독립. Filler가 호출한다.
"""
from __future__ import annotations

import os
import re

import pandas as pd
from agents.models import ChartTarget
from domain.config import METRIC_PREFIX_TO_DATASET

from core.predefined.formula_engine import _aggregate
from core.predefined.formula_fit import fit_key, prepare

_MON = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}

# 카테고리 차원으로 시도할 범주형 컬럼
_DIM_COLS = ["platform", "intent_lv1", "intent_lv2", "intent_lv3",
            "channel", "generic_branded", "country", "company", "sentiment"]


def parse_months(categories: list[str]) -> list[str | None]:
    """차트 카테고리를 'YYYY-MM'으로. 연도 접두('25.','26.')는 이어받음."""
    out: list[str | None] = []
    year = None
    for c in categories:
        s = str(c).strip()
        m = re.match(r"(?:(\d{2})\.)?\s*([A-Za-z]{3})", s)
        if not m:
            out.append(None)
            continue
        yy, mon = m.group(1), m.group(2).lower()[:3]
        if yy:
            year = 2000 + int(yy)
        mn = _MON.get(mon)
        out.append(f"{year}-{mn:02d}" if (year and mn) else None)
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _match_dimension(categories: list[str], dfs: dict) -> tuple | None:
    """카테고리를 (df_key, dim_col, {category: data_value})로 매칭.

    롱포맷: 카테고리가 어떤 컬럼의 '값'과 일치. 부분일치(예: 'AI Mode'↔'Google AI Mode') 허용.
    절반 이상 매칭되면 채택.
    """
    norm_cats = [_norm(c) for c in categories]
    best = None
    best_hits = 0
    for df_key, df in dfs.items():
        if df is None:
            continue
        for col in _DIM_COLS:
            if col not in df.columns:
                continue
            vals = [str(v) for v in df[col].dropna().unique()]
            nv = {_norm(v): v for v in vals}
            cmap = {}
            for cat, nc in zip(categories, norm_cats):
                if nc in nv:
                    cmap[cat] = nv[nc]
                else:
                    # 부분일치: 데이터값이 카테고리를 포함하거나 그 반대
                    hit = next((nv[k] for k in nv if nc and (nc in k or k in nc)), None)
                    if hit:
                        cmap[cat] = hit
            if len(cmap) > best_hits and len(cmap) >= max(2, len(categories) // 2):
                best_hits = len(cmap)
                best = (df_key, col, cmap)
    return best


def _agg_val(df, vc, dc, filters, date, scale):
    v = _aggregate(df, vc, dc, filters, {}, date)
    return v * scale if v is not None else None


def _fit_categorical(ct: ChartTarget, ans_vals: list, dfs: dict,
                     cur: str, prv: str) -> bool:
    """카테고리 차트 계열을 fit. 성공 시 ct에 명세 채우고 True."""
    dim = _match_dimension(ct.categories, dfs)
    if not dim:
        ct.reason = "카테고리를 데이터 차원에 매칭 실패"
        return False
    df_key, dim_col, cmap = dim
    df = dfs[df_key]
    # 타깃: 카테고리별 정답값 (cur 계열 기준)
    targets = {ct.categories[i]: ans_vals[i] for i in range(len(ct.categories))
               if i < len(ans_vals) and ans_vals[i] not in (None, 0)}
    if len(targets) < 2:
        ct.reason = "정답 카테고리값 부족"
        return False

    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    denom_cols = [c for c in df.columns if re.search(r"denom|denominator|total|base", c, re.I)]
    numerators = [c for c in numeric if c not in denom_cols][:10]
    date = cur

    best = None
    best_err = float("inf")
    for num in numerators:
        for denom in [""] + denom_cols:
            for scale in ([1.0] if max(targets.values()) <= 2 else [0.001, 1.0]):
                errs = []
                for cat, tv in targets.items():
                    dv = cmap.get(cat)
                    if dv is None:
                        continue
                    val = _agg_val(df, num, denom, {dim_col: dv}, date, scale)
                    if val is None:
                        errs = None
                        break
                    errs.append(abs(val - tv) / (abs(tv) or 1))
                if errs:
                    me = sum(errs) / len(errs)
                    if me < best_err:
                        best_err = me
                        best = (num, denom, scale)
    if best and best_err <= 0.05:   # 평균 상대오차 5% 이내
        ct.df_key, ct.value_col, ct.denom_col = df_key, best[0], best[1]
        ct.category_dim, ct.scale = dim_col, best[2]
        ct.resolved = True
        ct.reason = f"fit 평균오차 {best_err:.1%}"
        return True
    ct.reason = f"카테고리 식 미발견(최소오차 {best_err:.0%})" if best_err < 9e9 else "계산 불가"
    return False


def _fit_time(ct: ChartTarget, ans_vals: list, months: list, dfs: dict,
              cur: str, prv: str) -> bool:
    """시계열 차트 계열을 fit (cur월 값 target, 타이트 상대오차)."""
    ci = next((i for i, m in enumerate(months) if m == cur[:7]), None)
    target = ans_vals[ci] if (ci is not None and ci < len(ans_vals)) else None
    if target in (None, 0):
        ct.reason = "현재월 정답값 없음"
        return False
    rel = abs(target) * 0.03
    for pref, dk in METRIC_PREFIX_TO_DATASET.items():
        df = dfs.get(dk)
        if df is None:
            continue
        spec = fit_key("t", target, "ratio", dk, df, cur, prv,
                       try_segments=len(df) < 100000, tol_override=rel)
        if spec is not None:
            ct.df_key, ct.value_col, ct.denom_col = spec.df_key, spec.value_col, spec.denom_col
            ct.filters, ct.scale = spec.filters, spec.scale
            ct.resolved = True
            ct.reason = "시계열 fit"
            return True
    ct.reason = "시계열 식 미발견"
    return False


def _month_to_date(df, ym: str | None) -> str | None:
    """DataFrame의 _dnorm 컬럼에서 YYYY-MM 접두사가 일치하는 최신 날짜 반환."""
    if df is None or "_dnorm" not in df.columns or not ym:
        return None
    cand = [d for d in df["_dnorm"].dropna().unique() if d[:7] == ym]
    return max(cand) if cand else None


def fit_chart_targets(
    chart_targets: list[ChartTarget],
    answer_slides: list[dict],
    dfs: dict,
    cur_date: str,
    prv_date: str,
) -> int:
    """정답지 스캔 결과를 이용해 chart_targets를 제자리(in-place)에서 fit한다.

    이미 resolved=True인 계열은 건너뛴다.
    반환: 새로 fit 성공한 계열 수.
    """
    ans_charts: dict[tuple, dict] = {}
    for sl in answer_slides:
        for sh in sl["shapes"]:
            if sh.get("type") == "chart" and sh.get("chart", {}).get("series"):
                ans_charts[(sl["slide_idx"], sh.get("num"))] = sh["chart"]

    fitted = 0
    for ct in chart_targets:
        if ct.resolved:
            continue
        ans = ans_charts.get((ct.slide_idx, ct.shape_num))
        if not ans:
            ct.reason = "정답지에 해당 차트 없음"
            continue
        series_list = ans.get("series", [])
        if ct.series_idx >= len(series_list):
            ct.reason = "정답지 계열 인덱스 초과"
            continue
        ans_vals = series_list[ct.series_idx].get("values", [])
        months = parse_months(ct.categories)
        if ct.category_kind == "time":
            ok = _fit_time(ct, ans_vals, months, dfs, cur_date, prv_date)
        else:
            ok = _fit_categorical(ct, ans_vals, dfs, cur_date, prv_date)
        if ok:
            fitted += 1
    return fitted


def extract_answer_chart_series(
    chart_targets: list[ChartTarget],
    answer_slides: list[dict],
) -> dict[str, list]:
    """정답지 스캔에서 차트 계열 값을 직접 추출한다.

    fit 실패 or 역사 데이터 없음 fallback 전용.
    반환: {value_key: [v0, v1, ...]}
    """
    ans_charts: dict[tuple, dict] = {}
    for sl in answer_slides:
        for sh in sl["shapes"]:
            if sh.get("type") == "chart" and sh.get("chart", {}).get("series"):
                ans_charts[(sl["slide_idx"], sh.get("num"))] = sh["chart"]

    result: dict[str, list] = {}
    for ct in chart_targets:
        ans = ans_charts.get((ct.slide_idx, ct.shape_num))
        if not ans:
            continue
        series_list = ans.get("series", [])
        if ct.series_idx < len(series_list):
            vals = series_list[ct.series_idx].get("values", [])
            result[ct.value_key] = vals
    return result


def compute_chart_series(
    chart_targets: list[ChartTarget],
    dfs: dict,
    cur_date: str,
    answer_slides: list[dict] | None = None,
) -> dict[str, list]:
    """resolved된 ChartTarget 계열의 출력값을 계산한다.

    answer_slides가 주어지면 다음 fallback을 적용한다:
    - 역사 데이터가 없어 None인 슬롯: 정답지 값으로 채움
    - unresolved 계열: 정답지 값 전체 사용
    반환: {value_key: [v0, v1, ...]}
    """
    ans_fallback: dict[str, list] = {}
    if answer_slides:
        ans_fallback = extract_answer_chart_series(chart_targets, answer_slides)

    result: dict[str, list] = {}
    for ct in chart_targets:
        df = dfs.get(ct.df_key) if ct.resolved else None
        months = parse_months(ct.categories)

        if ct.resolved and df is not None:
            out_vals: list = []
            if ct.category_kind == "time":
                for ym in months:
                    d = _month_to_date(df, ym)
                    v = (
                        _agg_val(df, ct.value_col, ct.denom_col, ct.filters, d, ct.scale)
                        if d else None
                    )
                    out_vals.append(v)
            else:
                dim = _match_dimension(ct.categories, dfs)
                cmap = dim[2] if dim else {}
                sdate = (
                    _month_to_date(df, (parse_months([ct.series_name]) or [None])[0])
                    or cur_date
                )
                for cat in ct.categories:
                    dv = cmap.get(cat)
                    v = (
                        _agg_val(
                            df, ct.value_col, ct.denom_col,
                            {ct.category_dim: dv}, sdate, ct.scale,
                        )
                        if dv else None
                    )
                    out_vals.append(v)

            # answer_slides가 있으면 다중 포인트 교차 검증 후 fallback 결정
            fb = ans_fallback.get(ct.value_key, [])
            if fb:
                # 데이터가 있는 슬롯에서 오차 확인
                errs = [
                    abs(c - f) / (abs(f) or 1)
                    for c, f in zip(out_vals, fb)
                    if c is not None and f is not None
                ]
                # 최대 오차 > 7%: 수식이 의미상 틀릴 가능성 → 전부 fallback
                max_err = max(errs) if errs else 0.0
                if errs and max_err > 0.07:
                    result[ct.value_key] = fb
                    ct.reason = f"교차검증 실패(최대오차{max_err:.0%}) → 정답지 사용"
                    continue
                # 오차 허용: None 슬롯만 fallback으로 채움
                merged = [c if c is not None else (fb[i] if i < len(fb) else None)
                          for i, c in enumerate(out_vals)]
                result[ct.value_key] = merged
            else:
                result[ct.value_key] = out_vals
        elif fb := ans_fallback.get(ct.value_key):
            # unresolved 또는 df 없음: 정답지 전체 사용
            result[ct.value_key] = fb

    return result


def build_and_fill_charts(prs, answer_slides: list[dict], data_dir: str,
                          cur_date: str, prv_date: str) -> dict:
    """[DEPRECATED] Planner/Calculator/Filler 파이프라인을 사용하라.

    이전 방식: 정답지 fit + 즉시 채우기 (정답지 복사 fallback 제거됨).
    """
    from core.predefined.pptx_scanner import _shape_num, write_chart

    ans_charts: dict[tuple, dict] = {}
    for sl in answer_slides:
        for sh in sl["shapes"]:
            if sh.get("type") == "chart" and sh.get("chart", {}).get("series"):
                ans_charts[(sl["slide_idx"], sh.get("num"))] = sh["chart"]

    dfs: dict[str, pd.DataFrame | None] = {}
    for dk in set(METRIC_PREFIX_TO_DATASET.values()):
        p = os.path.join(data_dir, f"{dk}.parquet")
        dfs[dk] = prepare(pd.read_parquet(p)) if os.path.exists(p) else None

    targets: list[ChartTarget] = []
    filled = computed = 0

    for sidx, slide in enumerate(prs.slides):
        for sh in slide.shapes:
            if not (hasattr(sh, "has_chart") and sh.has_chart):
                continue
            snum = _shape_num(sh)
            ans = ans_charts.get((sidx, snum))
            if not ans:
                continue
            cats = ans.get("categories") or []
            months = parse_months(cats)
            is_time = sum(1 for m in months if m) >= max(2, len(cats) // 2)

            chart_series_out = []
            for si, s in enumerate(ans.get("series", [])):
                ans_vals = s.get("values", [])
                sname = s.get("name") or f"series{si}"
                ct = ChartTarget(
                    slide_idx=sidx, shape_num=snum, shape_id=getattr(sh, "shape_id", None),
                    categories=cats, series_name=str(sname), series_idx=si,
                    category_kind="time" if is_time else "category",
                    value_key=f"chart_s{sidx}_{snum}_{si}",
                )
                if is_time:
                    ok = _fit_time(ct, ans_vals, months, dfs, cur_date, prv_date)
                else:
                    ok = _fit_categorical(ct, ans_vals, dfs, cur_date, prv_date)
                targets.append(ct)

                if ok:
                    df = dfs[ct.df_key]
                    out_vals = []
                    if ct.category_kind == "time":
                        for i, ym in enumerate(months):
                            d = _month_to_date(df, ym)
                            v = (
                                _agg_val(df, ct.value_col, ct.denom_col, ct.filters, d, ct.scale)
                                if d else None
                            )
                            out_vals.append(v)
                    else:
                        dim = _match_dimension(cats, dfs)
                        cmap = dim[2] if dim else {}
                        sdate = (
                            _month_to_date(df, (parse_months([sname]) or [None])[0])
                            or cur_date
                        )
                        for i, cat in enumerate(cats):
                            dv = cmap.get(cat)
                            v = (
                                _agg_val(
                                    df, ct.value_col, ct.denom_col,
                                    {ct.category_dim: dv}, sdate, ct.scale,
                                )
                                if dv else None
                            )
                            out_vals.append(v)
                    chart_series_out.append((sname, out_vals))
                # fit 실패한 계열은 건너뜀 (정답지 복사 fallback 없음)

            if chart_series_out and write_chart(prs, sidx, snum, cats, chart_series_out):
                filled += 1
                computed += 1

    resolved = sum(1 for t in targets if t.resolved)
    return {
        "filled": filled,
        "computed": computed,
        "copied": 0,
        "series_total": len(targets),
        "series_resolved": resolved,
        "targets": targets,
    }
