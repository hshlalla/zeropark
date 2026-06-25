"""state.py — LangGraph 파이프라인 공유 상태.

## 리듀서 설계
- messages, errors: Annotated[list, reducer] → 각 노드가 새 항목만 반환하면 자동 누적
- 나머지 필드: 리듀서 없음 → 최신 값 override

## 파이프라인 흐름
  analyze_data → read_template → calculate_kpis → fill_pptx → verify_output
                                       ↑                ↑           │
                                       └── route_to="calculator"    │
                                                        └── route_to="filler"
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from agents.models import (
    SlideMapping,
    CalculationResult,
    VerificationResult,
    FillReport,
    ValidationIssue,
    KeySpecMapping,
)


class AgentState(TypedDict):
    # ── 입력 (override) ──────────────────────────────────────────────
    template_path: str
    answer_key_path: Optional[str]
    raw_data_dir: str
    output_path: Optional[str]
    target_month: Optional[str]

    # ── analyze_data 출력 (override) ────────────────────────────────
    data_schema: Optional[dict]
    data_cache_dir: Optional[str]            # parquet 캐시 폴더 경로
    data_coverage: Optional[dict]            # dict[str, DatasetCoverage] — Skill 1 출력

    # ── Pipeline Skill 0: KPI Conservation (override, 각 노드가 merge) ─
    kpi_counts: Optional[dict]               # {"reader": N, "calculator": M, "filler_in": K, "filler_out": L}
    chart_counts: Optional[dict]             # {"chart_total": N, "chart_filled": M, "chart_unfilled": K}

    # ── ① Reader 출력: 좌표 + KPI 키 매핑 (override) ────────────────
    slide_mapping: Optional[SlideMapping]

    # ── ① Planner 출력: KPI 계산 명세 집합 (override) ──────────────
    key_spec_mapping: Optional[KeySpecMapping]   # FormulaPlan

    # ── ② Calculator 출력: 구조화된 KPI 계산값 (override) ───────────
    calculation_result: Optional[CalculationResult]

    # ── ③ Filler 출력: PPT 파일 경로 (override) ─────────────────────
    execution_output_path: Optional[str]

    # ── Calculator 코드 캐시 경로 (override) ─────────────────────────
    kpi_code_path: Optional[str]      # core/agent_generated/calculators/kpi_calculator_{hash}.py

    # ── ④ Verifier 출력: 통과/실패 + 라우팅 피드백 (override) ────────
    verification_result: Optional[VerificationResult]

    # ── Manager Gate 제어 (override) ────────────────────────────────
    pending_gate: Optional[str]      # 다음 Manager가 실행할 게이트 이름

    # ── Verifier → Planner 자아 진화 (override) ─────────────────────
    failure_reports: Optional[list]   # [FailureReport dict] — 실패 key만 재합성

    # ── 재시도 제어 (override) ───────────────────────────────────────
    retry_count: int
    retry_feedback: Optional[str]   # 이전 검증에서 온 구체적 피드백

    # ── 레거시 호환 필드 (override) ──────────────────────────────────
    template_schema: Optional[dict]
    validation_issues: Optional[list[ValidationIssue]]
    fill_report: Optional[FillReport]
    generated_code_path: Optional[str]   # 레거시 코드 경로 (미사용 가능)

    # ── 누적 필드 (Annotated reducer → 각 노드가 새 항목만 반환) ────
    messages: Annotated[list[BaseMessage], add_messages]
    errors: Annotated[list[str], add]
    gate_results: Annotated[list, add]   # GateResult dict 목록 (Manager가 쌓음)
