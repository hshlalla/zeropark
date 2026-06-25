"""Reader Skill 2 — KPI Discovery Completeness 구현.

scan_placeholders()        : 템플릿에서 숫자 placeholder를 모두 탐지
check_mapping_completeness(): coverage 계산 → 95% 미만이면 FAIL
check_duplicate_kpis()     : 동일 KPI 여러 위치 사용 현황 보고
"""
from __future__ import annotations

import re
from collections import defaultdict

from agents.models import DiscoveryResult, PlaceholderLocation, SlideMapping

# ── Placeholder 탐지 패턴 ────────────────────────────────────────────────────

# 소형 테이블/텍스트 도형의 숫자 placeholder (≡ "0-valued" KPI 셀)
_PLACEHOLDER_RE = re.compile(
    r'[+-]?0\.0%p'     # ±0.0%p / 0.0%p (mom)
    r'|0\.0%(?!p)'     # 0.0% (pct, not %p)
    r'|0\.0[KB]'       # 0.0K / 0.0B (scale)
    r'|x0\.0'          # x0.0 (ratio)
    r'|x1\.0'          # x1.0 (ratio neutral)
)

# 미채우기 차트 시리즈명 (향후 지원 예정)
_CHART_UNFILLED_RE = re.compile(r'^(계열\d+|Series\d+|DataLabel)$')

# Reader의 테이블 행 제한과 동일하게 유지
_MAX_TABLE_ROWS = 30


def _format_hint(text: str) -> str:
    """placeholder 텍스트에서 format_type 추론."""
    if "%p" in text:
        return "mom"
    if "%" in text:
        return "pct"
    if re.search(r'[KB]', text):
        return "kval"
    if text.startswith("x"):
        return "ratio"
    return "raw"


def scan_placeholders(template_slides: list[dict]) -> list[PlaceholderLocation]:
    """템플릿 슬라이드에서 숫자 placeholder를 모두 탐지.

    포함:
    - 모든 테이블 셀 (≤30행)
    - 텍스트 도형
    포함 (별도 집계):
    - 미채우기 차트 (계열1/Series1 기준)
    """
    found: list[PlaceholderLocation] = []

    for slide in template_slides:
        idx = slide["slide_idx"]
        for sh in slide["shapes"]:
            stype = sh.get("type", "other")
            num = sh.get("num")
            name = sh.get("name", "")

            # ── 테이블 셀 ────────────────────────────────────────────────
            if stype == "table":
                grid = sh.get("grid", [])
                if len(grid) > _MAX_TABLE_ROWS:
                    continue  # 초대형 테이블(30행 초과)은 제외
                for r, row in enumerate(grid):
                    for c, cell_val in enumerate(row):
                        text = str(cell_val or "").strip()
                        if _PLACEHOLDER_RE.search(text):
                            found.append(PlaceholderLocation(
                                slide_idx=idx,
                                shape_num=num,
                                shape_name=name,
                                shape_type="table",
                                row=r,
                                col=c,
                                placeholder_text=text,
                                format_hint=_format_hint(text),
                            ))

            # ── 텍스트 도형 ───────────────────────────────────────────────
            elif stype == "text" and sh.get("text"):
                text = sh["text"].strip()
                if _PLACEHOLDER_RE.search(text):
                    found.append(PlaceholderLocation(
                        slide_idx=idx,
                        shape_num=num,
                        shape_name=name,
                        shape_type="text",
                        row=0,
                        col=0,
                        placeholder_text=text,
                        format_hint=_format_hint(text),
                    ))

            # ── 차트 (미채우기 감지) ──────────────────────────────────────
            elif stype == "chart":
                chart_info = sh.get("chart", {})
                series = chart_info.get("series", [])
                has_unfilled = any(
                    _CHART_UNFILLED_RE.match(str(s.get("name", "") or ""))
                    for s in series
                )
                all_zero = series and all(
                    all(v == 0.0 or v is None for v in s.get("values", []))
                    for s in series
                )
                if has_unfilled or all_zero:
                    found.append(PlaceholderLocation(
                        slide_idx=idx,
                        shape_num=num,
                        shape_name=name,
                        shape_type="chart",
                        row=0,
                        col=0,
                        placeholder_text=f"chart({chart_info.get('chart_type', '?')})",
                        format_hint="chart",
                    ))

    return found


def check_mapping_completeness(
    placeholders: list[PlaceholderLocation],
    mapping: SlideMapping,
) -> DiscoveryResult:
    """coverage 계산 후 95% 미만이면 FAIL.

    coverage = mapped / total  (소형 table + text 기준, chart 제외)
    """
    # 매핑 lookup set
    mapped_table: set[tuple] = set()
    mapped_text: set[tuple] = set()
    for t in mapping.targets:
        s_type = getattr(t, "shape_type", "table")
        if s_type == "text":
            mapped_text.add((t.slide_idx, t.shape_num))
        else:
            mapped_table.add((t.slide_idx, t.shape_num, t.row, t.col))

    table_total = table_mapped = 0
    text_total = text_mapped = 0
    chart_total = 0
    unmapped: list[PlaceholderLocation] = []

    for ph in placeholders:
        if ph.shape_type == "chart":
            chart_total += 1
            continue

        if ph.shape_type == "text":
            text_total += 1
            if (ph.slide_idx, ph.shape_num) in mapped_text:
                text_mapped += 1
            else:
                unmapped.append(ph)
        else:
            table_total += 1
            if (ph.slide_idx, ph.shape_num, ph.row, ph.col) in mapped_table:
                table_mapped += 1
            else:
                unmapped.append(ph)

    total = table_total + text_total
    mapped = table_mapped + text_mapped
    coverage = mapped / total if total > 0 else 1.0

    return DiscoveryResult(
        total_numeric_placeholders=total,
        mapped_placeholders=mapped,
        coverage=coverage,
        table_total=table_total,
        table_mapped=table_mapped,
        text_total=text_total,
        text_mapped=text_mapped,
        chart_total=chart_total,
        unmapped=unmapped,
        passed=coverage >= 0.95,
    )


def check_duplicate_kpis(mapping: SlideMapping) -> dict:
    """동일 KPI 키의 여러 위치 사용 현황 보고.

    Rule: 동일 KPI는 반드시 같은 value_key 사용 (절대 별도 생성 금지).
    """
    key_locs: dict[str, list] = defaultdict(list)
    for t in mapping.targets:
        key_locs[t.value_key].append({
            "slide_idx": t.slide_idx,
            "shape_num": t.shape_num,
            "row": t.row,
            "col": t.col,
        })

    multi = {k: v for k, v in key_locs.items() if len(v) > 1}
    single = {k: v for k, v in key_locs.items() if len(v) == 1}

    return {
        "total_unique_keys": len(key_locs),
        "multi_location_keys": len(multi),
        "single_location_keys": len(single),
        "examples": {k: v for k, v in list(multi.items())[:3]},
    }
