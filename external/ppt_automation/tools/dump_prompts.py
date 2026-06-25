"""dump_prompts.py – 슬라이드별 인사이트 프롬프트(실제 LLM 에 전송되는 문자열) 덤프.

LLM 을 호출하지 않고, production 과 '동일한' 조립 경로(insights.collect_jobs +
prompts.system_prompt/user_prompt)로 각 슬라이드의 system/user 프롬프트를 그대로 출력한다.
성과(07~13) 슬라이드 컨텍스트(_kpi_context)는 채워진 표값을 읽으므로, 먼저
build_report.fill_slides 로 슬라이드를 채운 뒤 프롬프트를 재현한다.

사용(저장소 루트에서):
  python tools/dump_prompts.py                 # docs/prompts_dump.md 로 저장
  python tools/dump_prompts.py 경로.md          # 지정 경로로 저장
"""
from __future__ import annotations

import os
import sys

from pptx import Presentation

# tools/ 하위에서 실행해도 루트의 build_report·geo_report 를 import 하도록 저장소 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_report  # noqa: E402
from geo_report import config  # noqa: E402
from geo_report.data.context import ReportContext  # noqa: E402
from geo_report.insights import core as insights, governing  # noqa: E402
from geo_report.insights import prompts as P  # noqa: E402


def _rule_name(rule: str) -> str:
    """gen['rule'] 문자열이 어떤 규칙 상수인지 이름으로 환원."""
    if not rule:
        return "(없음)"
    if rule == P.SLIDE4_RULE:
        return "SLIDE4_RULE"
    for k, v in P.SLIDE3_RULES.items():
        if rule == v:
            return f"SLIDE3_RULES['{k}']"
    for k, v in P.SECTION_RULES.items():
        if rule == v:
            return f"SECTION_RULES['{k}']"
    return "(custom)"


def _fit_kind(fit) -> str:
    return {"shape": "텍스트박스", "cell": "표 셀(단일)", "cells": "표 셀(묶음)"}.get(fit[0], fit[0])


def build_dump() -> str:
    aggs = build_report.get_aggregates()
    ctx = ReportContext.from_aggregates(aggs)
    prs = Presentation(config.BASE_TEMPLATE)
    # 성과 슬라이드 _kpi_context 가 '채워진' KPI 값을 읽도록 먼저 채운다(인사이트 제외).
    build_report.fill_slides(prs, aggs, ctx)

    gov = governing.Governing()
    jobs = insights.collect_jobs(prs, aggs, ctx, gov)
    # 3~5 요약 job 은 런타임에 '완성된 7~27 상세 슬라이드' 요약으로 re-grounding 된다 → 동일 반영.
    for j in jobs:
        if not j.get("views") and j["gen"]["section"] == "Summary":
            insights._reground_summary_job(prs, j)

    out = []
    out.append(f"# 인사이트 프롬프트 덤프 (기준월 {ctx.cur} / 전월 {ctx.prv})\n")
    out.append(f"- 거버닝 예시 사용: {gov.available} · 인사이트 타깃(job) {len(jobs)}개\n")
    out.append("> LLM 에 실제 전송되는 system/user 프롬프트를 그대로 재현한 것(생성 호출 없음).\n")
    out.append("> 주의: 3~5 요약은 '완성된 7~27 상세' 를 grounding 으로 쓰는데, 이 덤프는 LLM 미호출이라\n"
               "> 상세(7~27)의 '생성된 인사이트 문장'은 비어 있고 제목·KPI 값만 채워진 상태로 표시된다.\n")

    # 슬라이드(idx)별로 묶어 출력
    by_idx: dict[int, list] = {}
    for j in jobs:
        by_idx.setdefault(j["idx"], []).append(j)

    # 한 job → (라벨, gen) 목록. 슬7·8 고정 뷰 job 은 메시지1~4 뷰별 gen 을 펼친다.
    def _gens(j):
        if j.get("views"):
            return [(f"view:{vk}", g) for (vk, _), g in zip(insights._PERF_VIEWS, j["views"])]
        return [("", j["gen"])]

    for idx in sorted(by_idx):
        page = idx + 1
        j0 = by_idx[idx][0]
        section = _gens(j0)[0][1]["section"]
        out.append(f"\n---\n\n## 리포트 페이지 {page} (idx {idx}) — 섹션: {section}\n")
        k = 0
        for j in by_idx[idx]:
            for label, gen in _gens(j):
                k += 1
                sysp = P.system_prompt(gen["rule"])
                userp = P.user_prompt(**gen)
                tag = f" · {label}" if label else ""
                out.append(
                    f"\n### 타깃 {k}: topic='{j['topic']}'{tag} · "
                    f"country={j['country'] or '-'} · {_fit_kind(j['fit'])} · "
                    f"length={gen['length']} · n={gen['n']} · rule={_rule_name(gen['rule'])}\n"
                )
                out.append("**SYSTEM 프롬프트**\n\n```text\n" + sysp + "\n```\n")
                out.append("**USER 프롬프트**\n\n```text\n" + userp + "\n```\n")
    return "\n".join(out)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(config.BASE_DIR, "docs", "prompts_dump.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    text = build_dump()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"프롬프트 덤프 저장 → {out_path}")


if __name__ == "__main__":
    main()
