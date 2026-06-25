"""Manager 에이전트 — 결정론적 게이트 컨트롤러 (LLM 없음).

각 에이전트 노드가 완료되면 Manager가 산출물을 계약 기준으로 검증한다.
통과하면 다음 단계로, 실패하면 어느 노드로 되돌릴지 결정한다.

게이트 종류:
  after_data    → Gate 1: 데이터 커버리지
  after_mapping → Gate 2: SlideMapping coverage ≥ 95%
  after_plan    → Gate 3: FormulaPlan 완전성 (unresolved 없음)
  after_calc    → Gate 4: 계산 누락값 없음
  after_fill    → Gate 5: 채우기 완성도
  after_verify  → Gate 6: 검증 결과 + 라우팅 결정 (통과·종료 시 write_insights로)
  after_insight → Gate 7: 인사이트 작성 마무리 (항상 통과 → END)

라우팅 결정 원칙:
  - 통과(pass): _NEXT_ON_PASS[gate] 노드로 진행
  - 실패(fail) + retry_count < MAX_RETRIES: _FAIL_ROUTE[gate] 노드로 되돌림
  - 실패(fail) + retry_count >= MAX_RETRIES: 해당 단계 포기(passthrough 또는 end)

반복 제어 — 2단계 가드레일:
  · MAX_RETRIES(3)          : 단일 단계(mapping/plan/calc/fill)의 국소 소프트 캡.
                              한 단계가 3회 막히면 구조적 문제로 보고 포기한다.
  · HARD_ITERATION_LIMIT(7) : 전역 하드 리밋(절대 상한). 누적 반복이 이 값에 도달하면
                              어떤 게이트든 무조건 END로 보내고 errors에 Human-in-the-loop
                              시그널을 남긴다. 7회 이상 자동 반복은 이전/신규 수식 수정이
                              충돌해 협업 품질이 급락하므로 사람 관리자에게 토스한다.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage

from agents.models import GateResult
from agents.state import AgentState

MAX_RETRIES = 3              # 단일 단계 국소 재시도 소프트 캡
HARD_ITERATION_LIMIT = 7     # 전역 하드 리밋 — 도달 시 무조건 END + 사람 개입(HITL)

# verify 완료(통과/스킵/종료지시) 후 향하는 마무리 노드.
# 검증이 끝나면 채워진 값으로 인사이트 문장을 작성한 뒤 종료한다.
_AFTER_VERIFY_DONE = "write_insights"

# 각 게이트 통과 시 다음 노드
_NEXT_ON_PASS: dict[str, str] = {
    "after_data":    "read_template",
    "after_mapping": "plan_formulas",
    "after_plan":    "calculate_kpis",
    "after_calc":    "fill_pptx",
    "after_fill":    "verify_output",
    "after_verify":  _AFTER_VERIFY_DONE,
    "after_insight": "__end__",
}

# 각 게이트 실패 시 되돌아가는 노드 (재시도 대상)
_FAIL_ROUTE: dict[str, str] = {
    "after_data":    "__end__",       # 데이터 없으면 진행 불가
    "after_mapping": "read_template", # Reader 재실행
    "after_plan":    "plan_formulas", # Planner 재실행
    "after_calc":    "plan_formulas", # spec 수정 → Planner 재실행
    "after_fill":    "fill_pptx",     # Filler 재실행
    "after_verify":  _AFTER_VERIFY_DONE,  # 검증 끝 → 인사이트 작성 후 종료
    "after_insight": "__end__",       # 인사이트까지 끝 → 종료
}


def _gate_data(state: AgentState, retry: int) -> GateResult:
    """Gate 1: 데이터 커버리지 확인."""
    coverage = state.get("data_coverage") or {}
    errors = state.get("errors") or []
    schema = state.get("data_schema") or {}
    n_files = len(schema.get("file_schemas", []))

    data_errors = [e for e in errors if "데이터" in e or "parquet" in e.lower()]
    if data_errors:
        return GateResult(
            gate="after_data", passed=False, retry_count=retry,
            details=f"데이터 오류: {data_errors[0][:100]}",
            route_to="__end__",
        )

    empty_datasets = [k for k, v in coverage.items() if v.get("rows", 1) == 0]
    if empty_datasets:
        return GateResult(
            gate="after_data", passed=False, retry_count=retry,
            details=f"빈 데이터셋: {empty_datasets}",
            route_to="__end__",
        )

    return GateResult(
        gate="after_data", passed=True, retry_count=retry,
        details=f"데이터 {n_files}개 파일 확인 완료",
        route_to="read_template",
    )


def _gate_mapping(state: AgentState, retry: int) -> GateResult:
    """Gate 2: SlideMapping coverage ≥ 95%."""
    mapping = state.get("slide_mapping")
    errors = state.get("errors") or []

    if not mapping or not mapping.targets:
        route = _FAIL_ROUTE["after_mapping"] if retry < MAX_RETRIES else "__end__"
        return GateResult(
            gate="after_mapping", passed=False, retry_count=retry,
            details="SlideMapping 비어있음",
            route_to=route,
        )

    # Skill 2 경고는 errors에 누적됨 (reader/node.py가 추가)
    skill2_fails = [e for e in errors if "Skill 2" in e and "FAIL" in e]
    if skill2_fails:
        if retry < MAX_RETRIES:
            return GateResult(
                gate="after_mapping", passed=False, retry_count=retry,
                details=skill2_fails[-1][:120],
                route_to=_FAIL_ROUTE["after_mapping"],
            )
        # 최대 재시도 초과: 경고만 남기고 진행 (완전 차단보다 진행이 낫다)
        return GateResult(
            gate="after_mapping", passed=True, retry_count=retry,
            details=(
                f"coverage 부족이나 최대 재시도 도달 — "
                f"현재 mapping으로 진행 ({len(mapping.targets)}개 셀)"
            ),
            route_to="plan_formulas",
        )

    return GateResult(
        gate="after_mapping", passed=True, retry_count=retry,
        details=f"SlideMapping {len(mapping.targets)}개 셀, {len(mapping.unique_keys)}개 키",
        route_to="plan_formulas",
    )


def _gate_plan(state: AgentState, retry: int) -> GateResult:
    """Gate 3: FormulaPlan 완전성 (unresolved 없음)."""
    plan = state.get("key_spec_mapping")

    if not plan or not plan.specs:
        route = _FAIL_ROUTE["after_plan"] if retry < MAX_RETRIES else "__end__"
        return GateResult(
            gate="after_plan", passed=False, retry_count=retry,
            details="KeySpecMapping 비어있음",
            route_to=route,
        )

    u = len(plan.unresolved)
    if u > 0:
        route = _FAIL_ROUTE["after_plan"] if retry < MAX_RETRIES else "calculate_kpis"
        return GateResult(
            gate="after_plan", passed=False, retry_count=retry,
            details=f"FormulaPlan 미해결 {u}개 — Planner 재실행: {plan.unresolved[:5]}",
            route_to=route,
        )

    return GateResult(
        gate="after_plan", passed=True, retry_count=retry,
        details=f"FormulaPlan {len(plan.specs)}개 명세, 미해결 0개",
        route_to="calculate_kpis",
    )


def _gate_calc(state: AgentState, retry: int) -> GateResult:
    """Gate 4: 계산 결과 + 누락값 없음."""
    calc = state.get("calculation_result")
    mapping = state.get("slide_mapping")

    if not calc or not calc.values:
        route = _FAIL_ROUTE["after_calc"] if retry < MAX_RETRIES else "__end__"
        return GateResult(
            gate="after_calc", passed=False, retry_count=retry,
            details="CalculationResult 없음 — 계산 전면 실패",
            route_to=route,
        )

    total = len(calc.values)
    missing = []
    if mapping:
        missing = [k for k in mapping.unique_keys
                   if calc.values.get(k) is None or calc.values[k].raw_value is None]

    if missing:
        route = _FAIL_ROUTE["after_calc"] if retry < MAX_RETRIES else "fill_pptx"
        return GateResult(
            gate="after_calc", passed=False, retry_count=retry,
            details=f"계산 누락 {len(missing)}개 — Planner 재실행: {missing[:5]}",
            route_to=route,
        )

    return GateResult(
        gate="after_calc", passed=True, retry_count=retry,
        details=f"계산 {total}/{total}개 성공, 누락 0개",
        route_to="fill_pptx",
    )


def _gate_fill(state: AgentState, retry: int) -> GateResult:
    """Gate 5: 채우기 완성도 (표/텍스트 셀 + 차트)."""
    kpi_counts = state.get("kpi_counts") or {}
    filler_in = kpi_counts.get("filler_in", 0)
    filler_out = kpi_counts.get("filler_out", 0)

    cc = state.get("chart_counts") or {}
    c_total = cc.get("chart_total", 0)
    c_filled = cc.get("chart_filled", 0)
    c_unfilled = cc.get("chart_unfilled", 0)
    chart_str = f"차트 {c_filled}/{c_total}" + (f" (미채움 {c_unfilled})" if c_unfilled else "")

    unfilled_count = kpi_counts.get("unfilled_count", 0)

    # 셀 쓰기 손실 / 미채움 차트 / 잔여 placeholder 중 하나라도 있으면 실패
    cell_loss = filler_in > 0 and filler_out < filler_in
    if cell_loss or c_unfilled > 0 or unfilled_count > 0:
        route = _FAIL_ROUTE["after_fill"] if retry < MAX_RETRIES else "__end__"
        parts = []
        if cell_loss:
            parts.append(f"셀 미완 {filler_out}/{filler_in}")
        if c_unfilled > 0:
            parts.append(f"미채움 차트 {c_unfilled}개")
        if unfilled_count > 0:
            parts.append(f"잔여 placeholder {unfilled_count}개")
        return GateResult(
            gate="after_fill", passed=False, retry_count=retry,
            details="채우기 실패 — " + ", ".join(parts),
            route_to=route,
        )

    return GateResult(
        gate="after_fill", passed=True, retry_count=retry,
        details=f"채우기 완료: 셀 {filler_out}/{filler_in}, {chart_str}",
        route_to="verify_output",
    )


def _gate_verify(state: AgentState, retry: int) -> GateResult:
    """Gate 6: 검증 결과 판독 + 정밀 라우팅.

    Verifier가 이미 route_to를 결정했으므로 Manager는 이를 존중하되
    최대 재시도 초과 시 강제 종료한다.
    """
    ver = state.get("verification_result")

    if not ver:
        return GateResult(
            gate="after_verify", passed=True, retry_count=retry,
            details="VerificationResult 없음 — 검증 건너뜀",
            route_to=_AFTER_VERIFY_DONE,
        )

    if ver.passed:
        return GateResult(
            gate="after_verify", passed=True, retry_count=retry,
            details=f"검증 통과: {ver.ok_count}/{ver.total_checked}",
            route_to=_AFTER_VERIFY_DONE,
        )

    # 검증 실패지만 Verifier가 명시적으로 end를 지시한 경우(데이터 분포 차이 등) 종료.
    # (반복 횟수 상한은 manage_pipeline 최상위 HARD_ITERATION_LIMIT 가드레일이 담당하므로
    #  여기서 MAX_RETRIES로 자아 진화 루프를 조기 종료하지 않는다 — 진화에 여유를 준다.)
    if ver.route_to == "end":
        return GateResult(
            gate="after_verify", passed=False, retry_count=retry,
            details=(f"검증 실패 {ver.ok_count}/{ver.total_checked} — Verifier 종료 지시"),
            route_to=_AFTER_VERIFY_DONE,
        )

    # ── 정밀 라우팅 ──────────────────────────────────────────────────
    # 수식/계산 오류(wrong_value·missing_value)는 코드가 아니라 '명세'가 틀린 것이므로
    # Calculator가 아니라 Planner로 되돌려 FormulaPlan을 자아 진화시킨다.
    # 셀 위치/포맷 오류는 Filler 소관.
    #   Verifier route_to "calculator" → plan_formulas (명세 진화)
    #                     "filler"     → fill_pptx     (셀 위치/포맷 수정)
    next_node = "plan_formulas" if ver.route_to == "calculator" else "fill_pptx"
    reason = ("수식/계산 오류 → Planner 자아 진화"
              if next_node == "plan_formulas" else "셀 위치/포맷 오류 → Filler 재실행")
    return GateResult(
        gate="after_verify", passed=False, retry_count=retry,
        details=(f"검증 실패: {ver.ok_count}/{ver.total_checked}, "
                 f"{len(ver.issues)}개 불일치 → {next_node} ({reason})"),
        route_to=next_node,
    )


def _gate_insight(state: AgentState, retry: int) -> GateResult:
    """Gate 7: 인사이트 작성 마무리 게이트 (항상 통과 — 산출물 품질 가산 단계).

    인사이트는 부가 단계라 실패해도 파이프라인을 막지 않는다. 항상 END로 보낸다.
    """
    return GateResult(
        gate="after_insight", passed=True, retry_count=retry,
        details="인사이트 작성 단계 완료",
        route_to="__end__",
    )


_GATE_HANDLERS = {
    "after_data":    _gate_data,
    "after_mapping": _gate_mapping,
    "after_plan":    _gate_plan,
    "after_calc":    _gate_calc,
    "after_fill":    _gate_fill,
    "after_verify":  _gate_verify,
    "after_insight": _gate_insight,
}


def manage_pipeline(state: AgentState) -> dict:
    """결정론적 게이트 컨트롤러.

    pending_gate에 해당하는 게이트를 실행하고 GateResult를 gate_results에 쌓는다.
    실패 시 retry_count를 증가시키고 route_to를 결정한다.
    """
    gate = state.get("pending_gate") or ""
    retry = state.get("retry_count", 0)

    # ── 하드 리밋 가드레일 (최우선·결정론적) ──────────────────────────────
    # 어느 게이트든 누적 반복(retry_count)이 HARD_ITERATION_LIMIT에 도달하면
    # 게이트 검사 없이 무조건 END로 보내고 Human-in-the-loop 시그널을 남긴다.
    # 7회 이상 자동 반복은 수식 수정 충돌로 품질이 급락 → 토큰 낭비이므로 사람에게 토스.
    if retry >= HARD_ITERATION_LIMIT:
        hitl = (
            f"[HUMAN-IN-THE-LOOP REQUIRED] 자동 재시도 {retry}회가 하드 리밋"
            f"({HARD_ITERATION_LIMIT})에 도달했습니다. 반복 수정 충돌로 자동 협업 품질이 "
            f"저하되어 파이프라인을 강제 종료합니다. 마지막 게이트='{gate or '?'}'. "
            f"사람 관리자의 검토(수식·매핑 수동 확인)가 필요합니다."
        )
        result = GateResult(
            gate=gate or "guardrail", passed=False, retry_count=retry,
            details=hitl, route_to="__end__",
        )
        print(f"[Manager] ⛔ {hitl}")
        return {
            "gate_results": [result.model_dump()],
            "pending_gate": None,
            "retry_count": retry,
            "errors": [hitl],
            "messages": [AIMessage(
                content=(
                    f"⛔ 하드 리밋({HARD_ITERATION_LIMIT}) 도달 — "
                    f"사람 검토 필요, 파이프라인 종료"
                ),
                name="Manager",
            )],
        }

    handler = _GATE_HANDLERS.get(gate)
    if handler is None:
        result = GateResult(
            gate=gate or "unknown", passed=True, retry_count=retry,
            details=f"알 수 없는 게이트 '{gate}' — pass through",
            route_to="__end__",
        )
    else:
        result = handler(state, retry)

    icon = "✓" if result.passed else "✗"
    print(f"[Manager] [{icon}] Gate={gate} → route={result.route_to} | {result.details}")

    new_retry = retry + (0 if result.passed else 1)

    updates: dict = {
        "gate_results": [result.model_dump()],
        "pending_gate": None,
        "retry_count": new_retry,
        "messages": [AIMessage(
            content=f"[Gate {gate}] {'통과' if result.passed else '실패'} → {result.route_to}",
            name="Manager",
        )],
    }

    # ── 게이트 실패로 노드에 되돌릴 때, 그 노드가 캐시를 무시하고 재생성하도록
    #    실패 사유를 retry_feedback으로 전달한다.
    #    (after_verify는 Verifier가 이미 구체적 LLM 피드백을 설정했으므로 보존)
    if not result.passed and result.route_to != "__end__" and gate != "after_verify":
        updates["retry_feedback"] = (
            f"[Manager Gate '{gate}' 실패 — 재시도 {new_retry}/{MAX_RETRIES}]\n"
            f"{result.details}\n"
            f"이전 결과를 그대로 재사용하지 말고 위 문제를 해결해 다시 생성하라."
        )

    return updates


def route_from_manager(state: AgentState) -> str:
    """LangGraph 조건부 엣지: 마지막 GateResult의 route_to를 반환."""
    gate_results = state.get("gate_results") or []
    if not gate_results:
        return "__end__"
    last = gate_results[-1]
    return last.get("route_to", "__end__")
