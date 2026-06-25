"""③ Filler 에이전트 — PPT 직접 채우기 (결정론적, LLM 없음).

SlideMapping.targets를 순회해 write_cell로 각 셀에 CalculationResult 값을 채운다.
LLM·코드 생성·subprocess 없음.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime

from core.predefined.pptx_scanner import write_cell, write_chart, write_text_shape
from langchain_core.messages import AIMessage
from pptx import Presentation

from agents.models import CalculationResult, SlideMapping
from agents.state import AgentState
from agents.utils import load_skills

from .fill_validator import check_fill_completeness, scan_unfilled

_SKILLS = load_skills("filler")


def fill_pptx(state: AgentState) -> dict:
    """SlideMapping + CalculationResult → PPT 직접 채우기.

    반환: execution_output_path (override), messages (append)
    """
    mapping: SlideMapping | None = state.get("slide_mapping")
    calc: CalculationResult | None = state.get("calculation_result")
    feedback = state.get("retry_feedback", "")

    if not mapping or not mapping.targets:
        return {"errors": ["slide_mapping 없음"]}
    if not calc:
        return {"errors": ["calculation_result 없음"]}

    template_path = state["template_path"]
    out_path = state.get("execution_output_path") or state.get("output_path")
    if not out_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "output",
        )
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"filled_{ts}.pptx")

    if feedback:
        print("[Filler] 재시도 (retry_feedback 있음) — 동일 로직 재실행")

    print(f"[Filler] PPT 채우기: {len(mapping.targets)}개 셀 → {os.path.basename(out_path)}")

    shutil.copy2(template_path, out_path)
    prs = Presentation(out_path)

    ok_count = 0
    failed: list[str] = []

    for t in mapping.targets:
        value = calc.get_formatted(t.value_key)
        s_type = getattr(t, "shape_type", "table")
        if s_type == "text":
            success = write_text_shape(prs, t.slide_idx, t.shape_num, value,
                                       shape_id=t.shape_id)
        else:
            success = write_cell(prs, t.slide_idx, t.shape_num, t.row, t.col, value,
                                 shape_id=t.shape_id)
        if success:
            ok_count += 1
        else:
            failed.append(
                f"slide={t.slide_idx} shape={t.shape_num}"
                f" [{t.row},{t.col}] key={t.value_key!r}"
            )

    if failed:
        for f in failed:
            print(f"  [경고] 셀 쓰기 실패: {f}")

    # ── 차트 채우기 (CalculationResult.chart_series 기반, 파이프라인 통합) ──────
    chart_targets = mapping.chart_targets or []
    chart_series = calc.chart_series if calc.chart_series else {}
    chart_counts = {"chart_total": 0, "chart_filled": 0, "chart_unfilled": 0}

    if chart_targets:
        from collections import defaultdict
        chart_groups: dict = defaultdict(list)
        for ct in chart_targets:
            chart_groups[(ct.slide_idx, ct.shape_num)].append(ct)

        c_total = len(chart_groups)
        c_filled = 0
        c_skipped = 0
        for (sidx, snum), cts in chart_groups.items():
            cts_sorted = sorted(cts, key=lambda c: c.series_idx)
            series_data = []
            complete = True
            for ct in cts_sorted:
                vals = chart_series.get(ct.value_key)
                if vals is None:
                    complete = False
                    break
                # None 값은 0.0으로 대체 (빈 막대)
                clean_vals = [v if v is not None else 0.0 for v in vals]
                series_data.append((ct.series_name, clean_vals))
            if not complete:
                c_skipped += 1
                print(f"  [차트 스킵] slide={sidx} shape={snum}: chart_series 없음")
                continue
            cats = cts_sorted[0].categories
            shape_id = cts_sorted[0].shape_id
            ok = write_chart(prs, sidx, snum, cats, series_data, shape_id=shape_id)
            if ok:
                c_filled += 1
            else:
                c_skipped += 1
                print(f"  [차트 실패] slide={sidx} shape={snum}: write_chart 반환 False")
        chart_counts = {
            "chart_total": c_total,
            "chart_filled": c_filled,
            "chart_unfilled": c_skipped,
        }
        print(f"[Filler] 차트 채우기: {c_filled}/{c_total}개 채움"
              + (f" (스킵 {c_skipped}개)" if c_skipped else ""))

    unfilled: list[dict] = []

    # ── Pipeline Skill 0: KPI Conservation 기록 ───────────────────────────────
    _kpi_counts = {
        **(state.get("kpi_counts") or {}),
        "filler_in": len(mapping.targets),
        "filler_out": ok_count,
    }
    print(f"[Pipeline] KPI Conservation [filler_in]: {len(mapping.targets)}")
    print(f"[Pipeline] KPI Conservation [filler_out]: {ok_count}")

    # ── Skill 4-A: Fill Completeness Check ───────────────────────────────────
    if _SKILLS:
        ok, warns = check_fill_completeness(len(mapping.targets), ok_count)
        if not ok:
            for w in warns:
                print(f"[Filler] ⚠ {w}")
        else:
            print(f"[Filler] [Skill 4] ✓ Fill Completeness: {ok_count}/{len(mapping.targets)}")

    # ── Skill 4-C: Unfilled Scan (저장 전 최종 검증) ─────────────────────────
    if _SKILLS:
        unfilled = scan_unfilled(prs)
        if unfilled:
            print(
                f"[Filler] ⚠ [Skill 4] FAIL Unfilled Scan: {len(unfilled)}개 잔여 placeholder 발견"
            )
            for u in unfilled[:10]:
                loc = f"row={u['row']},col={u['col']}" if u["type"] == "table" else ""
                print(f"  slide={u['slide_idx']} shape={u['shape']!r} {loc}: {u['text']!r}")
            if len(unfilled) > 10:
                print(f"  ... 외 {len(unfilled) - 10}개 더")
        else:
            print("[Filler] [Skill 4] ✓ Unfilled Scan: 잔여 placeholder 없음")

    prs.save(out_path)

    msg = (f"PPT 채우기 완료: {ok_count}/{len(mapping.targets)}개 셀 "
           f"→ {os.path.basename(out_path)}"
           + (f" (실패 {len(failed)}개)" if failed else "")
           + (f" (잔여placeholder {len(unfilled)}개)" if _SKILLS and unfilled else ""))
    print(f"[Filler] {msg}")

    return {
        "execution_output_path": out_path,
        "output_path": out_path,
        "kpi_counts": {**_kpi_counts, "unfilled_count": len(unfilled)},
        "chart_counts": chart_counts,
        "pending_gate": "after_fill",
        "messages": [AIMessage(content=msg, name="Filler")],
    }
