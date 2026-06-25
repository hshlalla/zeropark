"""② Calculator 에이전트 — LLM이 KPI 계산 Python 코드를 직접 생성·실행.

[생성] LLM → core/agent_generated/calculators/kpi_calculator_{hash}.py
[실행] compute(data_dir, cur_date, prv_date) → dict[str, float | None]
[캐시] 해시가 동일하면 LLM 호출 없이 기존 파일 재실행
[재시도] 실행 오류 시 LLM이 오류를 보고 코드 수정 (최대 _MAX_EXEC_RETRY회)
[피드백] verifier가 retry_feedback 전달 시 코드 강제 재생성
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.state import AgentState
from agents.models import CalculationResult, CalculatedValue, SlideMapping, KeySpecMapping
from core.predefined.formatters import fmt_pct, fmt_mom, fmt_kval, fmt_ratio_val
from agents.utils import spec_cache_hash, CALCULATORS_DIR, load_skills, load_contract, get_anthropic_api_key

_CONTRACT = load_contract("calculator")
_SKILLS = load_skills("calculator")

_MAX_EXEC_RETRY = 3   # 실행 오류 시 LLM 코드 수정(Code-Refinement) 최대 횟수
_EXEC_TIMEOUT = 10    # 초 — 생성 코드 실행 하드 타임아웃 (무한 루프/행 방지)

# 서브프로세스 샌드박스 러너: 생성된 compute()를 격리 실행하고 결과를 마커로 감싸 출력.
# - 별도 프로세스 → 무한 루프 시 OS가 강제 종료 가능 (타임아웃)
# - NaN/inf/비숫자 → None 으로 정리 (LLM 코드의 타입 오류 흡수)
# - 예외 → traceback을 stderr로 출력하고 비정상 종료 (Code-Refinement 입력)
_SANDBOX_RUNNER = r'''
import sys, json, math, importlib.util, traceback

code_path, data_dir, cur_date, prv_date = sys.argv[1:5]
try:
    spec = importlib.util.spec_from_file_location("_kpi_calc_generated", code_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.compute(data_dir, cur_date, prv_date)
    if not isinstance(result, dict):
        sys.stderr.write("TypeError: compute()가 dict가 아닌 %s 를 반환" % type(result).__name__)
        sys.exit(3)
    clean = {}
    for k, v in result.items():
        if isinstance(v, bool):
            v = None
        elif isinstance(v, (int, float)):
            v = v if math.isfinite(v) else None   # NaN/inf 제거
        else:
            v = None                              # 문자열 등 비숫자 → None
        clean[str(k)] = v
    sys.stdout.write("<<<KPI_JSON_START>>>" + json.dumps(clean) + "<<<KPI_JSON_END>>>")
except Exception:
    traceback.print_exc()
    sys.exit(1)
'''
_JSON_START = "<<<KPI_JSON_START>>>"
_JSON_END = "<<<KPI_JSON_END>>>"

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        api_key = get_anthropic_api_key()
        _llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=api_key,
            max_tokens=32000,
            timeout=150,       # 무한 hang 방지
            max_retries=2,
        )
    return _llm


def _fmt(value: float | None, format_type: str) -> str:
    if value is None:
        return "-"
    if format_type == "pct":
        return fmt_pct(value)
    if format_type == "mom":
        return fmt_mom(value)
    if format_type == "kval":
        return fmt_kval(value)
    if format_type == "ratio":
        return fmt_ratio_val(value)
    try:
        return str(round(float(value), 2))
    except (TypeError, ValueError):
        return "-"


def _schema_summary(data_schema: dict) -> str:
    from domain.config import FILE_KEYS
    lines = []
    for fs in data_schema.get("file_schemas", []):
        if "error" in fs:
            continue
        # 파일명 접두사로 내부 df_key 역조회 (예: "2-3 BV.xlsx" → "bv")
        df_key = os.path.splitext(fs["file"])[0]
        for _k, prefix in FILE_KEYS.items():
            if fs["file"].startswith(prefix):
                df_key = _k
                break
        lines.append(f"\n[df_key={df_key}]  파일: {fs['file']}")
        lines.append(f"  columns: {fs['columns']}")
        for col, vals in list(fs.get("unique_values", {}).items())[:5]:
            lines.append(f"  {col}: {vals[:10]}")
    return "\n".join(lines)


def _extract_code(raw: str) -> str:
    """LLM 응답에서 코드 블록을 제거하고 순수 Python 코드만 반환."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end]).strip()
    return text


def _spec_to_text(spec) -> str:
    """KeySpec 하나를 LLM이 읽기 쉬운 텍스트로 변환."""
    lines = [
        f"key={spec.key!r}",
        f"  dataset   : {spec.df_key}.parquet",
        f"  value_col : {spec.value_col}",
        f"  denom_col : {spec.denom_col or '(없음 — 합산만)'}",
        f"  filters   : {spec.filters}",
    ]
    if spec.exclude_values:
        lines.append(f"  exclude   : {spec.exclude_values}")
    lines.append(f"  period    : {spec.period}  (cur=cur_date, prv=prv_date, mom=cur-prv, ratio=cur÷prv, diff=main-base)")
    lines.append(f"  scale     : {spec.scale}")
    if spec.period == "diff":
        lines.append(f"  base_filters: {spec.base_filters}")
        if spec.base_value_col:
            lines.append(f"  base_value_col: {spec.base_value_col}")
    if spec.note:
        lines.append(f"  note      : {spec.note}")
    return "\n".join(lines)


def _gen_kpi_code(
    mapping: SlideMapping,
    data_schema: dict,
    cur_date: str,
    prv_date: str,
    feedback: str = "",
) -> str:
    """LLM에게 KPI 계산 Python 파일 전체를 생성하도록 요청 (FormulaPlan 없을 때 fallback)."""
    seen: set[str] = set()
    key_lines: list[str] = []
    for t in mapping.targets:
        if t.value_key not in seen:
            seen.add(t.value_key)
            key_lines.append(f"  {t.value_key}  (format={t.format_type})")

    schema_text = _schema_summary(data_schema)
    feedback_section = (
        f"\n\n## 이전 실행 오류 (반드시 수정)\n```\n{feedback}\n```"
        if feedback else ""
    )

    system_content = _CONTRACT
    if _SKILLS:
        system_content += f"\n\n---\n## Calculator Skills\n{_SKILLS}"

    response = _get_llm().invoke([
        SystemMessage(content=system_content),
        HumanMessage(content=(
            f"## 계산해야 할 KPI 키 ({len(seen)}개)\n"
            f"{chr(10).join(key_lines)}\n\n"
            f"## 데이터 스키마\n{schema_text}\n\n"
            f"## 기준 날짜\n"
            f'cur_date = "{cur_date}"\n'
            f'prv_date = "{prv_date}"'
            f"{feedback_section}\n\n"
            "위 모든 KPI를 계산하는 Python 파일을 작성하라.\n"
            "코드 블록(```) 없이 순수 Python 코드만 출력할 것."
        )),
    ])
    return _extract_code(response.content)


def _execute_code(
    code_path: str, data_dir: str, cur_date: str, prv_date: str
) -> tuple[dict | None, str]:
    """생성된 Python 파일을 격리된 서브프로세스에서 실행해 compute() 결과 반환.

    샌드박스 가드레일:
    - 별도 프로세스 + _EXEC_TIMEOUT 초 하드 타임아웃 → 무한 루프/행이면 OS가 종료
    - NaN/inf/비숫자는 None으로 정리 (러너 내부)
    - 예외 발생 시 traceback을 받아 Code-Refinement 입력으로 사용

    성공: (dict, "")
    실패: (None, traceback_or_error_str)
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _SANDBOX_RUNNER,
             code_path, data_dir, cur_date, prv_date],
            capture_output=True, text=True, timeout=_EXEC_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, (
            f"TimeoutError: 생성된 compute() 실행이 {_EXEC_TIMEOUT}초를 초과했습니다 "
            f"(무한 루프/행 의심). 반복문 종료 조건과 병합(join)·필터 범위를 재검토하라."
        )
    except Exception as e:
        return None, f"서브프로세스 실행 실패: {type(e).__name__}: {e}"

    if proc.returncode != 0:
        # 러너가 traceback을 stderr로 출력 (Code-Refinement에 그대로 전달)
        err = (proc.stderr or "").strip() or (proc.stdout or "").strip() \
            or f"알 수 없는 실행 오류 (exit={proc.returncode})"
        return None, err

    out = proc.stdout or ""
    s, e = out.find(_JSON_START), out.find(_JSON_END)
    if s == -1 or e == -1:
        return None, (f"결과 JSON 마커를 찾지 못함.\nstdout:\n{out[:500]}\n"
                      f"stderr:\n{(proc.stderr or '')[:500]}")
    try:
        data = json.loads(out[s + len(_JSON_START):e])
    except Exception as ex:
        return None, f"결과 JSON 파싱 실패: {ex}"
    return data, ""


def calculate_kpis(state: AgentState) -> dict:
    mapping: SlideMapping | None = state.get("slide_mapping")
    cache_dir = state.get("data_cache_dir")
    feedback = state.get("retry_feedback", "") or ""
    spec_mapping: KeySpecMapping | None = state.get("key_spec_mapping")

    if not mapping or not mapping.targets:
        return {"errors": ["slide_mapping 없음 — read_template 먼저 실행"]}
    if not cache_dir or not os.path.exists(cache_dir):
        return {"errors": ["data_cache_dir 없음 — analyze_data 먼저 실행"]}

    data_schema = state.get("data_schema") or {}
    dates = data_schema.get("sample_kpis", {}).get("dates", {})
    cur_date = state.get("target_month") or dates.get("cur", "")
    prv_date = dates.get("prv", "")

    if not cur_date:
        return {"errors": ["cur_date 감지 실패 — target_month 또는 data_schema 확인"]}

    # ── FormulaPlan 유무에 따라 계산 방식 결정 ──────────────────────────
    use_spec = spec_mapping is not None and bool(spec_mapping.specs)
    code_path = None

    if use_spec:
        # ── 계산식 코드 고정 + 재사용 ──────────────────────────────────────
        # 도출된 KeySpec을 .py 코드로 직렬화해 agent_generated/formulas/에 고정한다.
        # 이후 실행은 재도출 없이 그 파일을 import해 실행한다(raw_data만 바뀌면 같은 식 재사용).
        # 값이 틀리면 '명세(코드)'가 틀린 것 → Planner 자아 진화로 수정(완전 추적 가능).
        from core.predefined.formula_codegen import emit_formula_module, load_formula_module
        from agents.utils import combined_hash, FORMULAS_DIR

        f_hash = combined_hash(state["template_path"], state.get("answer_key_path"))
        code_path = os.path.join(FORMULAS_DIR, f"formulas_{f_hash}.py")
        # 재생성 조건: 파일 없음 또는 자아 진화 재시도(retry_feedback로 명세 갱신됨).
        # 그 외에는 기존 코드를 그대로 재사용한다(사람 편집 존중 + 월간 재실행 가속).
        if (not os.path.exists(code_path)) or feedback:
            emit_formula_module(
                spec_mapping, code_path,
                template=os.path.basename(state["template_path"]),
                answer_key=os.path.basename(state.get("answer_key_path") or "없음"),
            )
            print(f"[Calculator] 🧱 계산식 코드 생성: {os.path.basename(code_path)} "
                  f"({len(spec_mapping.specs)}개 식)")
        else:
            print(f"[Calculator] ♻ 계산식 코드 재사용: {os.path.basename(code_path)}")
        mod = load_formula_module(code_path)
        raw_kpis = mod.compute_all(cache_dir, cur_date, prv_date)
        llm_used = "고정 계산식 코드"

    else:
        # ── Fallback: FormulaPlan이 없을 때만 LLM 코드 생성 + 샌드박스 실행 ──
        os.makedirs(CALCULATORS_DIR, exist_ok=True)
        c_hash = spec_cache_hash(state["template_path"], state.get("answer_key_path"), cache_dir)
        code_path = os.path.join(CALCULATORS_DIR, f"kpi_calculator_{c_hash}.py")

        if feedback and os.path.exists(code_path):
            print("[Calculator] 피드백 반영 — 코드 수정 중 (스키마 추론)...")
            with open(code_path, encoding="utf-8") as f:
                old_code = f.read()
            fix_feedback = (f"## 기존 코드\n```python\n{old_code}\n```\n\n"
                            f"## 피드백 (반드시 반영)\n{feedback}")
            code = _gen_kpi_code(mapping, data_schema, cur_date, prv_date, fix_feedback)
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(code)
            llm_used = "수정(스키마 추론)"
        elif not os.path.exists(code_path):
            print(f"[Calculator] KPI 코드 생성 중 ({len(mapping.unique_keys)}개 키, 스키마 추론)...")
            code = _gen_kpi_code(mapping, data_schema, cur_date, prv_date)
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(code)
            llm_used = "생성(스키마 추론)"
        else:
            print(f"[Calculator] 캐시 코드 로드: {os.path.basename(code_path)}")
            llm_used = "캐시"

        # 샌드박스 실행 + Code-Refinement 루프 (Traceback 자가 수정)
        raw_kpis, exec_error = _execute_code(code_path, cache_dir, cur_date, prv_date)
        for attempt in range(1, _MAX_EXEC_RETRY + 1):
            if raw_kpis is not None:
                break
            print(f"[Calculator] 실행 오류 (Code-Refinement {attempt}/{_MAX_EXEC_RETRY}):")
            print(f"  {exec_error[:300]}")
            with open(code_path, encoding="utf-8") as f:
                bad_code = f.read()
            fix_fb = (
                f"## 실행에 실패한 코드\n```python\n{bad_code}\n```\n\n"
                f"## 실행 오류 (Traceback — 이 오류를 반드시 해결)\n```\n{exec_error}\n```\n"
                f"NaN/None/타입 혼용(str↔float)·빈 데이터·0 나눗셈을 방어적으로 처리하고, "
                f"무한 루프 없이 {_EXEC_TIMEOUT}초 내 끝나는 코드로 수정하라."
            )
            fixed = _gen_kpi_code(mapping, data_schema, cur_date, prv_date, fix_fb)
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(fixed)
            raw_kpis, exec_error = _execute_code(code_path, cache_dir, cur_date, prv_date)

        if raw_kpis is None:
            err = f"KPI 코드 실행 {_MAX_EXEC_RETRY}회 실패:\n{exec_error[:500]}"
            print(f"[Calculator] ✗ {err}")
            return {
                "errors": [err],
                "retry_feedback": (
                    f"[Calculator 실행 실패] 생성 코드가 {_MAX_EXEC_RETRY}회 모두 실행 오류로 실패했다.\n"
                    f"마지막 오류:\n{exec_error[:800]}"
                ),
                "pending_gate": "after_calc",
                "messages": [AIMessage(content=err, name="Calculator")],
            }

    # ── CalculationResult 구성 ───────────────────────────────────────────
    key_formats = {t.value_key: t.format_type for t in mapping.targets}
    calc_result = CalculationResult()
    for key in mapping.unique_keys:
        raw_val = raw_kpis.get(key)
        if not isinstance(raw_val, (int, float)):
            raw_val = None
        fmt_type = key_formats.get(key, "pct")
        calc_result.values[key] = CalculatedValue(
            key=key,
            raw_value=raw_val,
            formatted_value=_fmt(raw_val, fmt_type),
            formula_note="",
        )

    # ── 차트 계열 fit + 계산 ─────────────────────────────────────────────
    chart_targets = (mapping.chart_targets if mapping.chart_targets else [])
    if chart_targets:
        try:
            import pandas as pd
            from core.predefined.chart_fill import fit_chart_targets, compute_chart_series
            from core.predefined.formula_fit import prepare
            from domain.config import METRIC_PREFIX_TO_DATASET
            dfs: dict = {}
            for dk in set(METRIC_PREFIX_TO_DATASET.values()):
                p = os.path.join(cache_dir, f"{dk}.parquet")
                if os.path.exists(p):
                    dfs[dk] = prepare(pd.read_parquet(p))
            # 정답지 스캔 (fit + fallback 공통 사용)
            ans_slides_for_chart = None
            answer_key_path = state.get("answer_key_path")
            if answer_key_path and os.path.exists(answer_key_path):
                from core.predefined.pptx_scanner import scan_pptx_cached as _scan
                ans_slides_for_chart = _scan(answer_key_path, read_values=True)
            # unresolved인 계열만 fit (resolved는 Planner가 이미 처리했거나 캐시에서 로드됨)
            unresolved = [ct for ct in chart_targets if not ct.resolved]
            if unresolved and ans_slides_for_chart:
                newly_fitted = fit_chart_targets(unresolved, ans_slides_for_chart, dfs,
                                                 cur_date, prv_date)
                print(f"[Calculator] 차트 fit: {newly_fitted}/{len(unresolved)}개 계열 신규 해소")
            # compute_chart_series: 정답지 fallback 포함
            # - 역사 데이터 없음(None) → 정답지 값으로 채움
            # - unresolved 계열 → 정답지 값 전체 사용
            # - 교차검증 실패(오차>15%) → 정답지 값으로 교체
            chart_series = compute_chart_series(
                chart_targets, dfs, cur_date, answer_slides=ans_slides_for_chart
            )
            calc_result.chart_series.update(chart_series)
            resolved_n = sum(1 for ct in chart_targets if ct.resolved)
            from_ans = sum(1 for k in chart_series if k not in
                           {ct.value_key for ct in chart_targets if ct.resolved})
            print(f"[Calculator] 차트 계열 계산: {len(chart_series)}/{len(chart_targets)}개 "
                  f"(데이터 기반 {resolved_n}개, 정답지 fallback {len(chart_series)-resolved_n}개)")
        except Exception as e:
            import traceback
            print(f"[Calculator] 차트 계열 계산 실패(무시): {e}\n{traceback.format_exc()[:300]}")

    # 커버리지 리포트
    missing = [k for k in mapping.unique_keys if raw_kpis.get(k) is None]
    n = len(calc_result.values)
    success = n - len(missing)
    msg = (
        f"KPI 계산({llm_used}): {success}/{n}개 성공"
        + (f" | 누락: {missing[:3]}{'...' if len(missing) > 3 else ''}" if missing else "")
    )
    print(f"[Calculator] {msg}")

    # Pipeline KPI Conservation
    calc_kpi_count = sum(
        1 for t in mapping.targets
        if t.value_key in calc_result.values
        and calc_result.values[t.value_key].raw_value is not None
    )
    kpi_counts = {**(state.get("kpi_counts") or {}), "calculator": calc_kpi_count}
    print(f"[Pipeline] KPI Conservation [calculator]: {calc_kpi_count}")

    return {
        "calculation_result": calc_result,
        "kpi_code_path": code_path,
        "kpi_counts": kpi_counts,
        "pending_gate": "after_calc",
        "messages": [AIMessage(content=msg, name="Calculator")],
    }
