"""graph.py — LangGraph StateGraph 오케스트레이터.

파이프라인 (Manager가 게이트를 통해 모든 흐름 제어):

  analyze_data → manage → read_template → manage → plan_formulas
       → manage → calculate_kpis → manage → fill_pptx
       → manage → verify_output  → manage → write_insights → manage → END

  manage 노드가 pending_gate를 읽어 다음 노드를 결정:
    · 통과(pass) → _NEXT_ON_PASS[gate] 진행
    · 실패(fail) + 재시도 가능 → _FAIL_ROUTE[gate] 되돌아감
    · 실패(fail) + 재시도 초과 → END 강제 종료

각 에이전트의 단일 책임:
  analyze_data    → Excel 스키마 + parquet 캐시 생성
  read_template   → PPT 좌표 + KPI 키 매핑 (SlideMapping)
  plan_formulas   → KPI 계산 명세 집합 (FormulaPlan = KeySpecMapping)
  calculate_kpis  → FormulaPlan 기반 KPI 계산 (CalculationResult)
  fill_pptx       → PPT 셀 채우기
  verify_output   → 정답지 비교 → VerificationResult + route_to 권고
  write_insights  → 채워진 KPI 값 근거로 슬라이드 인사이트 문장 자동 작성
  manage          → 게이트 통과 확인 + 라우팅 결정 (결정론적, LLM 없음)
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.state import AgentState
from agents.nodes.data_analyzer import analyze_data
from agents.nodes.reader import read_template
from agents.nodes.planner import plan_formulas
from agents.nodes.calculator import calculate_kpis
from agents.nodes.filler import fill_pptx
from agents.nodes.verifier import verify_output
from agents.nodes.insight_writer import write_insights
from agents.nodes.manager import manage_pipeline, route_from_manager


def build_graph():
    g = StateGraph(AgentState)

    # ── 노드 등록 ──────────────────────────────────────────────────────
    g.add_node("analyze_data",   analyze_data)
    g.add_node("read_template",  read_template)
    g.add_node("plan_formulas",  plan_formulas)
    g.add_node("calculate_kpis", calculate_kpis)
    g.add_node("fill_pptx",      fill_pptx)
    g.add_node("verify_output",  verify_output)
    g.add_node("write_insights", write_insights)
    g.add_node("manage",         manage_pipeline)

    # ── 진입점: analyze_data → manage ─────────────────────────────────
    g.set_entry_point("analyze_data")

    # ── 모든 에이전트 → manage ────────────────────────────────────────
    g.add_edge("analyze_data",   "manage")
    g.add_edge("read_template",  "manage")
    g.add_edge("plan_formulas",  "manage")
    g.add_edge("calculate_kpis", "manage")
    g.add_edge("fill_pptx",      "manage")
    g.add_edge("verify_output",  "manage")
    g.add_edge("write_insights", "manage")

    # ── manage → 조건부 엣지 (route_from_manager가 경로 결정) ──────────
    g.add_conditional_edges(
        "manage",
        route_from_manager,
        {
            "read_template":  "read_template",
            "plan_formulas":  "plan_formulas",
            "calculate_kpis": "calculate_kpis",
            "fill_pptx":      "fill_pptx",
            "verify_output":  "verify_output",
            "write_insights": "write_insights",
            "__end__":        END,
        },
    )

    return g.compile()


_app = None


def get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app
