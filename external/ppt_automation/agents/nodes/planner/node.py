"""Planner 에이전트 — KPI 계산 명세(FormulaPlan = KeySpecMapping) 생성.

Calculator가 코드를 짜기 전에 "무엇을 어떻게 계산할지"를 먼저 구조화한다.
[생성] LLM → KeySpecMapping (구조체)
[캐시] generated/plans/formula_plan_{hash}.json — 동일 입력이면 재사용

Manager Gate 3(after_plan)이 명세 완전성을 확인:
- unresolved 키가 있으면 재시도 요청

[자아 진화 — Cognitive Evolving]
Verifier가 wrong_value/missing_value를 보고하면 Manager가 Planner로 되돌린다.
이때 Planner는 자신의 직전 계획(key_spec_mapping)과 실패 기록(verification_result)을
직접 대조해, 실패한 key의 명세(필터/분자/분모/df_key/period)를 스스로 반성·수정한다.
실패하지 않은 key는 그대로 유지한다.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from domain.config import FILE_KEYS
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.models import KeySpecMapping, SlideMapping, VerificationResult
from agents.state import AgentState
from agents.utils import PLANS_DIR, combined_hash, get_anthropic_api_key, load_contract

_CONTRACT = load_contract("planner")

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        api_key = get_anthropic_api_key()
        _llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=api_key,
            max_tokens=16000,
            timeout=180,       # 배치 생성 헤드룸 (무한 hang 방지)
            max_retries=2,
        )
    return _llm


def _schema_summary_for_planner(data_schema: dict) -> str:
    """데이터 스키마를 Planner LLM이 읽기 쉬운 형태로 변환.

    파일 접두사 대신 내부 df_key를 헤더에 표시해 KeySpec.df_key 작성을 돕는다.
    """
    reverse_keys = {v: k for k, v in FILE_KEYS.items()}  # "2-3" → "bv"

    def _to_df_key(filename: str) -> str:
        for prefix, key in FILE_KEYS.items():
            if (filename.startswith(key) or filename.startswith(key + " ")
                    or filename.startswith(key + ".")):
                return prefix
        # 역방향: 파일명 접두사로 역조회
        for file_prefix, df_key in reverse_keys.items():
            if filename.startswith(file_prefix):
                return df_key
        return os.path.splitext(filename)[0]

    lines = []
    for fs in data_schema.get("file_schemas", []):
        if "error" in fs:
            continue
        df_key = _to_df_key(fs["file"])
        lines.append(f"\n[df_key={df_key}]  파일: {fs['file']}")
        lines.append(f"  columns: {fs['columns']}")
        for col, vals in list(fs.get("unique_values", {}).items()):
            lines.append(f"  {col}: {vals[:15]}")
    return "\n".join(lines)


# 한 번의 LLM 호출에 담을 최대 KPI 키 수.
# 키가 많으면(예: 2000+) 단일 호출은 max_tokens/timeout을 초과하므로 배치로 나눈다.
# 80개면 출력이 ~8K 토큰 → 180초 타임아웃 내 안전.
_BATCH_SIZE = 80
# 배치 LLM 호출 동시 실행 수 (벽시계 단축). 과도하면 rate limit 위험.
_MAX_PARALLEL = 4


def _run_batches(llm, batches: list[list[str]], key_line_map: dict[str, str],
                 schema_text: str, cur_date: str, prv_date: str,
                 extra_section_fn, instruction: str, label: str):
    """배치들을 병렬 실행하고 (specs, unresolved)를 누적 반환. 배치 실패는 격리.

    extra_section_fn(batch) → 해당 배치의 추가 프롬프트 섹션(피드백/진화 컨텍스트).
    한 배치가 실패하면 그 키들을 unresolved로 넘기고 계속 진행한다.
    """
    specs_all: list = []
    unresolved_all: list = []

    def _one(batch: list[str]):
        text = "\n".join(key_line_map.get(k, f"  {k}") for k in batch)
        try:
            partial = _invoke_specs(llm, text, schema_text, cur_date, prv_date,
                                    extra_section=extra_section_fn(batch),
                                    instruction=instruction)
            return list(partial.specs), list(partial.unresolved), None
        except Exception as e:
            return None, batch, str(e)[:120]   # 실패 → 키를 unresolved로

    total = len(batches)
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as ex:
        futs = {ex.submit(_one, b): b for b in batches}
        done = 0
        for fut in as_completed(futs):
            specs, unres, err = fut.result()
            done += 1
            if specs is None:
                unresolved_all.extend(unres)
                print(
                    f"[Planner]   {label} {done}/{total}: "
                    f"✗ 실패({err}) → {len(unres)}개 unresolved"
                )
            else:
                specs_all.extend(specs)
                unresolved_all.extend(unres)
                print(
                    f"[Planner]   {label} {done}/{total}: "
                    f"+{len(specs)}개 (누적 {len(specs_all)})"
                )
    return specs_all, unresolved_all


def _key_line_map(mapping: SlideMapping) -> dict[str, str]:
    """value_key → 설명 라인 (format/context 포함). 순서 보존, 중복 제거."""
    out: dict[str, str] = {}
    for t in mapping.targets:
        out.setdefault(
            t.value_key,
            f"  {t.value_key}  (format={t.format_type}, context={t.context!r})",
        )
    return out


def _invoke_specs(llm, key_list_text: str, schema_text: str,
                  cur_date: str, prv_date: str,
                  extra_section: str, instruction: str) -> KeySpecMapping:
    """KeySpec 생성 LLM 1회 호출 (배치/진화 공통)."""
    return llm.invoke([
        SystemMessage(content=_CONTRACT),
        HumanMessage(content=(
            f"## 명세를 작성할 KPI 키\n{key_list_text}\n\n"
            f"## 데이터 스키마 (df_key별 컬럼·유니크값)\n{schema_text}\n\n"
            f"## 날짜\n"
            f'cur_date = "{cur_date}"\n'
            f'prv_date = "{prv_date}"'
            f"{extra_section}\n\n"
            "계산 코드를 쓰지 말고 명세(KeySpec 구조체)만 출력할 것.\n"
            f"{instruction}"
        )),
    ])


def _spec_one_line(spec) -> str:
    """KeySpec 하나를 한 줄 요약 (이전 계획 보존용)."""
    base = (f"df_key={spec.df_key}, value_col={spec.value_col}, "
            f"denom_col={spec.denom_col or '(없음)'}, filters={spec.filters}, "
            f"period={spec.period}, scale={spec.scale}")
    if spec.exclude_values:
        base += f", exclude={spec.exclude_values}"
    if spec.period == "diff":
        base += f", base_filters={spec.base_filters}"
        if spec.base_value_col:
            base += f", base_value_col={spec.base_value_col}"
    return base


def _build_evolution_context(prev_plan: KeySpecMapping,
                             ver_result: VerificationResult,
                             only_keys: set[str] | None = None) -> str:
    """자아 진화 — 직전 계획과 검증 실패를 대조해 어느 key의 명세를 의심할지 정리.

    wrong_value / missing_value 실패만 대상으로 한다 (셀 위치/포맷 문제는 Filler 소관).
    only_keys가 주어지면 해당 key들만 포함한다 (배치 처리용).
    """
    if prev_plan is None or ver_result is None or not ver_result.issues:
        return ""

    fails_by_key: dict[str, list] = defaultdict(list)
    for iss in ver_result.issues:
        if iss.root_cause in ("wrong_value", "missing_value") and iss.value_key:
            if only_keys is not None and iss.value_key not in only_keys:
                continue
            fails_by_key[iss.value_key].append(iss)

    if not fails_by_key:
        return ""

    lines = ["\n\n## ⚠ 자아 진화(Self-Evolving) — 직전 계획의 실패를 반성하라",
             "아래는 네가 직전에 세운 명세로 계산한 값이 정답지(expected)와 어긋난 기록이다.",
             "실패한 key의 KeySpec(df_key/필터/분자/분모/period/scale)을 의심하고 수정하라.",
             "실패하지 않은 key는 직전 명세 그대로 유지하라.\n"]

    for key, issues in fails_by_key.items():
        prev_spec = prev_plan.get(key)
        lines.append(f"### key={key!r}")
        if prev_spec:
            lines.append(f"  - 직전 명세: {_spec_one_line(prev_spec)}")
        else:
            lines.append(
                "  - 직전 명세: (없음 → 이 key는 직전 계획에서 누락됐다. 새로 작성하라)"
            )
        for iss in issues[:3]:
            lines.append(f"  - 실패: expected={iss.expected!r} actual={iss.actual!r} "
                         f"cause={iss.root_cause}")
        causes = {i.root_cause for i in issues}
        if "missing_value" in causes:
            lines.append(
                "  - 진단: actual이 비어있음 → 필터 값이 데이터에 없거나"
                "(예: country/플랫폼 코드 불일치), "
                "df_key 또는 분자/분모 컬럼이 틀렸을 가능성. "
                "스키마의 unique_values를 다시 확인하라."
            )
        if "wrong_value" in causes:
            lines.append("  - 진단: 값이 어긋남 → 분자/분모 컬럼, 필터 범위, "
                         "scale(100 vs 1), period(cur/mom/ratio/diff)를 재검토하라.")
    return "\n".join(lines)


# ── 정답지 기반 결정론적 식 구성 (LLM 없음) ──────────────────────────────────


def _build_fit_plan(mapping: SlideMapping, answer_key_path: str, cache_dir: str,
                    cur_date: str, prv_date: str) -> tuple[KeySpecMapping, dict]:
    """Metric Resolver + Catalog 기반 KeySpec 생성.

    각 value_key → resolve(MetricId) → catalog.build_keyspec:
      · ratio family(bv/sentiment, vs_* diff) → 명시적 KeySpec
      · fit family(rv/rs)                     → 정답지 값 target으로 식 역산
      · ranking/chart/unsupported            → 미해결로 보고
    """
    from collections import defaultdict

    import pandas as pd
    from core.predefined.formula_critic import FormulaCritic
    from core.predefined.formula_fit import build_targets, prepare

    # ── 역할별 컴포넌트 (단일 책임) ───────────────────────────────────
    from core.predefined.formula_synthesizer import FormulaSynthesizer
    from core.predefined.formula_validator import FormulaValidator
    from core.predefined.metric_resolver import entity_filters, resolve
    from core.predefined.pptx_scanner import scan_pptx_cached as scan_pptx
    from domain.metric_catalog import build_keyspec

    from agents.models import KeySpec

    synthesizer = FormulaSynthesizer()   # 공식 후보 생성
    validator = FormulaValidator()       # raw_data로 계산·검증
    fcritic = FormulaCritic()            # 의미 비판

    ans = scan_pptx(answer_key_path, read_values=True)
    targets = build_targets(ans, [t.model_dump() for t in mapping.targets])
    conflicts = [k for k, v in targets.items() if v["n_distinct"] > 1]

    _dfs: dict[str, "pd.DataFrame"] = {}

    def _load(dk: str):
        if dk and dk not in _dfs:
            path = os.path.join(cache_dir, f"{dk}.parquet")
            _dfs[dk] = prepare(pd.read_parquet(path)) if os.path.exists(path) else None
        return _dfs.get(dk)

    # 공유 메모리 (검증식 재사용 / 실패후보 스킵 — 같은 실수 반복 방지)
    from core.predefined.shared_memory import get_memory
    mem = get_memory()
    mem_metrics: list = []   # metric_catalog bulk
    mem_attempts: list = []  # formula_attempts bulk

    # fit 패밀리: Synthesizer→Validator→Critic 역할을 명시적으로 호출
    _CONF_THRESHOLD = 0.8

    def _sig(c: dict) -> str:
        return f"{c['num']}|{c['denom']}|{c['scale']}"

    def _synth_validate_critic(key, mid, dk, df, info):
        """역할 오케스트레이션: (메모리 재사용) → 후보생성 → 의미비판 → 계산검증.

        반환: (KeySpec|None, confidence, reason)
        """
        if df is None or info is None:
            return None, 0.0, "데이터/정답지값 없음"
        target = info["target"]
        if target in (None, 0):
            return None, 0.0, "정답지값 없음"

        # ⓪ 메모리 재사용: 이미 검증된 고신뢰 식이 있으면 합성 생략
        cached = mem.validated_formula(key, min_conf=0.85)
        if cached:
            spec = KeySpec(key=key, df_key=cached.get("df_key", dk),
                           value_col=cached["num"], denom_col=cached.get("denom", ""),
                           filters=entity_filters(mid), period=mid.period,
                           scale=cached.get("scale", 1.0), note="memory reuse")
            return spec, 0.9, "memory"

        # ① Synthesizer (후보 생성)
        cands = synthesizer.candidates(mid, df, dk, info["fmt"])
        # ② Critic 선필터 + 이전 reject 후보 스킵 (메모리)
        rejected = mem.rejected_signatures(key)
        cands = [c for c in cands if fcritic.passes(c, mid) and _sig(c) not in rejected]
        if not cands:
            return None, 0.0, "Critic/메모리 필터 후 후보 없음"
        # ③ Validator: 엔티티·날짜 1회 슬라이스 후 후보별 오차
        ent = df
        for col, v in entity_filters(mid).items():
            if col in ent.columns:
                ent = ent[ent[col].astype(str) == str(v)]
        cur_sub = ent[ent["_dnorm"] == cur_date] if "_dnorm" in ent.columns else ent
        scored = [(c, validator.score_on(c, cur_sub, target)) for c in cands]
        scored = [(c, e) for c, e in scored if e != float("inf")]
        if not scored:
            return None, 0.0, "정답지 값 재현 식 없음"
        scored.sort(key=lambda x: x[1])
        best, best_err = scored[0]
        # ④ Critic 최종검토 — evidence(계산값·오차·대안 후보)까지 보고 판단
        value = validator.compute_on(best, cur_sub)
        ok, c_reason, penalty = fcritic.review(
            best, mid, {"value": value, "error": best_err, "alternatives": scored[1:4]})
        if not ok:
            return None, 0.0, f"Critic 탈락: {c_reason}"
        conf = max(0.0, 1.0 - best_err) * penalty
        if conf < _CONF_THRESHOLD:
            return (
                None, conf,
                f"confidence {conf:.2f} < {_CONF_THRESHOLD} "
                f"(오차 {best_err:.0%}, {c_reason})"
            )
        spec = KeySpec(key=key, df_key=best["df_key"], value_col=best["num"],
                       denom_col=best["denom"], filters=entity_filters(mid),
                       period=mid.period, scale=best["scale"],
                       note=f"synth conf={conf:.2f} err={best_err:.0%}")
        return spec, conf, "ok"

    by_prefix: dict[str, list] = defaultdict(lambda: [0, 0])
    by_strategy: dict[str, int] = defaultdict(int)
    specs: list = []
    unresolved: list[str] = []
    reasons: dict[str, str] = {}
    decisions: list[dict] = []   # Thought→Plan→Action 기록

    def _decide(key, mid, sdef, *, analysis, plan_s, action, conf, resolved):
        decisions.append({
            "value_key": key,
            "analysis_summary": analysis,
            "plan": plan_s,
            "action_result": action,
            "confidence": round(conf, 2),
            "resolved": resolved,
        })

    # 각 value_key: Resolver(Thought) → Catalog/후보(Plan) → 합성·검증(Action)
    for key in mapping.unique_keys:
        mid = resolve(key)
        by_prefix[mid.metric_family][1] += 1
        spec, reason, sdef = build_keyspec(mid)
        by_strategy[sdef["strategy"]] += 1
        info = targets.get(key)
        # Thought: 문맥/암시 요약
        analysis = (f"family={mid.metric_family} entity={mid.entity} country={mid.country} "
                    f"period={mid.period} comp={mid.comparison}"
                    + (f" extras={mid.extras}" if mid.extras else "")
                    + (f" | 정답지값={info['target']}" if info else ""))

        if spec is not None:
            specs.append(spec)
            by_prefix[mid.metric_family][0] += 1
            _decide(key, mid, sdef,
                    analysis=analysis,
                    plan_s=(
                        f"카탈로그 ratio: df={spec.df_key} 분자={spec.value_col} "
                        f"분모={spec.denom_col} 필터={spec.filters} period={spec.period}"
                    ),
                    action=f"명시정의 채택 ({spec.note or 'catalog'})",
                    conf=0.95, resolved=True)
            mem_metrics.append((
                key, mid.metric_family,
                {"num": spec.value_col, "denom": spec.denom_col,
                 "filters": spec.filters, "period": spec.period, "scale": spec.scale},
                0.95, "catalog 명시정의",
            ))
            mem_attempts.append((
                key,
                {"num": spec.value_col, "denom": spec.denom_col, "scale": spec.scale},
                None, info["target"] if info else None, None, "accepted", "catalog",
            ))
        elif reason == "fit_required":
            # rv/rs — Synthesizer → Critic → Validator 역할 오케스트레이션
            dk = sdef.get("dataset")
            df = _load(dk)
            fspec, conf, sreason = _synth_validate_critic(key, mid, dk, df, info)
            if fspec is not None:
                specs.append(fspec)
                by_prefix[mid.metric_family][0] += 1
                _decide(key, mid, sdef,
                        analysis=analysis,
                        plan_s=f"df={dk} 후보 생성→의미비판→정답지 교차검증",
                        action=(
                            f"채택: 분자={fspec.value_col} 분모={fspec.denom_col} "
                            f"scale={fspec.scale} ({fspec.note})"
                        ),
                        conf=conf, resolved=True)
                mem_metrics.append((
                    key, mid.metric_family,
                    {"num": fspec.value_col, "denom": fspec.denom_col,
                     "filters": fspec.filters, "period": fspec.period, "scale": fspec.scale},
                    conf, fspec.note,
                ))
                mem_attempts.append((
                    key,
                    {"num": fspec.value_col, "denom": fspec.denom_col, "scale": fspec.scale},
                    None, info["target"] if info else None, None, "accepted", "fit",
                ))
            else:
                unresolved.append(key)
                reasons[key] = sreason
                _decide(key, mid, sdef,
                        analysis=analysis,
                        plan_s=f"df={dk} 후보 생성→검증",
                        action=f"미해결: {sreason}", conf=conf, resolved=False)
                mem_attempts.append((key, "n/a", None, info["target"] if info else None,
                                     None, "rejected", sreason))
        else:
            unresolved.append(key)
            reasons[key] = reason
            _decide(key, mid, sdef,
                    analysis=analysis,
                    plan_s=f"strategy={sdef['strategy']}",
                    action=f"미해결: {reason}", conf=0.0, resolved=False)

    # ── 공유 메모리 기록 (bulk) — 검증된 식·시도 이력 누적 ────────────────
    try:
        mem.upsert_metrics_bulk(mem_metrics)
        mem.log_attempts_bulk(mem_attempts)
        print(f"[Planner] 공유 메모리: metric_catalog {len(mem_metrics)}건, "
              f"formula_attempts {len(mem_attempts)}건 기록")
    except Exception as e:
        print(f"[Planner] 메모리 기록 실패(무시): {e}")

    plan = KeySpecMapping(specs=specs, unresolved=unresolved)
    report = {
        "fit": len(specs), "total": len(mapping.unique_keys),
        "by_prefix": dict(by_prefix), "by_strategy": dict(by_strategy),
        "unresolved_reasons": reasons, "conflicts": conflicts,
        "decisions": decisions,
    }
    return plan, report


def _resynthesize_failed(prev_plan: KeySpecMapping, failure_reports: list,
                         answer_key_path: str, cache_dir: str,
                         cur_date: str, prv_date: str) -> tuple[KeySpecMapping, int]:
    """FailureReport의 실패 key만 더 넓은 후보로 재합성해 prev_plan에 병합.

    Verifier → Planner 자아 진화: 실패한 key만 다시 공식 후보 생성(wider).
    반환: (새 KeySpecMapping, 교체된 key 수)
    """
    import pandas as pd
    from core.predefined.formula_critic import FormulaCritic
    from core.predefined.formula_fit import parse_value, prepare
    from core.predefined.formula_synthesizer import FormulaSynthesizer
    from core.predefined.formula_validator import FormulaValidator
    from core.predefined.metric_resolver import entity_filters, resolve
    from domain.metric_catalog import get_strategy

    synth, val, crit = FormulaSynthesizer(), FormulaValidator(), FormulaCritic()
    # FailureReport의 expected를 target으로 사용
    _dfs: dict = {}

    def _load(dk):
        if dk and dk not in _dfs:
            p = os.path.join(cache_dir, f"{dk}.parquet")
            _dfs[dk] = prepare(pd.read_parquet(p)) if os.path.exists(p) else None
        return _dfs.get(dk)

    from core.predefined.shared_memory import get_memory

    from agents.models import KeySpec
    mem = get_memory()

    def _sig(c):
        return f"{c['num']}|{c['denom']}|{c['scale']}"

    merged = {s.key: s for s in prev_plan.specs}
    replaced = 0
    for fr in failure_reports:
        key = fr["key"]
        mid = resolve(key)
        sdef = get_strategy(mid)
        dk = sdef.get("dataset")
        df = _load(dk)
        tgt = parse_value(fr.get("expected", ""))
        if df is None or tgt in (None, 0):
            continue
        # 직전(실패한) 식을 메모리에 reject 기록 → 다음부터 그 후보 스킵
        old = merged.get(key)
        if old:
            mem.log_attempt(key, {"num": old.value_col, "denom": old.denom_col, "scale": old.scale},
                            None, tgt, None, "rejected", f"verify 실패: {fr.get('actual')}")
        rejected = mem.rejected_signatures(key)
        # 넓은 후보(top=20) + 의미비판 + 이전 reject 스킵
        cands = [c for c in synth.candidates(mid, df, dk, "ratio", top=20)
                 if crit.passes(c, mid) and _sig(c) not in rejected]
        ent = df
        for col, v in entity_filters(mid).items():
            if col in ent.columns:
                ent = ent[ent[col].astype(str) == str(v)]
        sub = ent[ent["_dnorm"] == cur_date] if "_dnorm" in ent.columns else ent
        scored = sorted(((c, val.score_on(c, sub, tgt)) for c in cands), key=lambda x: x[1])
        scored = [(c, e) for c, e in scored if e != float("inf")]
        if not scored:
            continue
        best, err = scored[0]
        ok, _r, pen = crit.review(best, mid, {"value": val.compute_on(best, sub),
                                              "error": err, "alternatives": scored[1:4]})
        if ok and (1 - err) * pen >= 0.8:
            merged[key] = KeySpec(key=key, df_key=best["df_key"], value_col=best["num"],
                                  denom_col=best["denom"], filters=entity_filters(mid),
                                  period=mid.period, scale=best["scale"],
                                  note=f"evolve err={err:.0%}")
            # 새로 검증된 식을 메모리에 accepted로 기록(재사용)
            mem.upsert_metric(key, mid.metric_family,
                              {"df_key": best["df_key"], "num": best["num"],
                               "denom": best["denom"], "scale": best["scale"]},
                              (1 - err) * pen, f"evolve err={err:.0%}")
            replaced += 1
    return (
        KeySpecMapping(specs=list(merged.values()), unresolved=list(prev_plan.unresolved)),
        replaced,
    )


def _format_unfit_report(report: dict) -> str:
    """정의 불가 키를 카테고리별로 정리한 사람용 리포트."""
    from collections import defaultdict
    by_reason: dict[str, list] = defaultdict(list)
    for key, reason in report["unresolved_reasons"].items():
        by_reason[reason].append(key)
    lines = [f"[Planner] 정답지 기반 식 구성: {report['fit']}/{report['total']}개 자동 생성"]
    for pref, (f, t) in sorted(report["by_prefix"].items(), key=lambda x: -x[1][1]):
        lines.append(f"  · {pref:12s} {f}/{t} ({f*100//max(t,1)}%)")
    if report["conflicts"]:
        lines.append(f"  ⚠ 매핑 불일치(같은 key 다른 값) {len(report['conflicts'])}개")
    if by_reason:
        lines.append(f"  ── 정의 불가 {sum(len(v) for v in by_reason.values())}개 (보고) ──")
        for reason, keys in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            lines.append(f"    [{len(keys)}개] {reason}  예: {keys[:2]}")
    return "\n".join(lines)


def plan_formulas(state: AgentState) -> dict:
    """SlideMapping unique_keys + data_schema → KeySpecMapping (FormulaPlan) 생성.

    캐시 히트 시 LLM 없이 JSON 로드.
    pending_gate = "after_plan" 설정 → Manager Gate 3 실행 요청.
    """
    mapping: SlideMapping | None = state.get("slide_mapping")
    data_schema = state.get("data_schema") or {}
    cache_dir = state.get("data_cache_dir") or ""
    feedback = state.get("retry_feedback", "") or ""
    prev_plan: KeySpecMapping | None = state.get("key_spec_mapping")
    ver_result: VerificationResult | None = state.get("verification_result")

    if not mapping or not mapping.targets:
        return {"errors": ["slide_mapping 없음 — read_template 먼저 실행"]}

    # 자아 진화 모드: 직전 계획 + 검증 실패가 있으면 명세를 반성·수정한다
    evolution_text = _build_evolution_context(prev_plan, ver_result)
    is_evolving = bool(evolution_text)

    dates = data_schema.get("sample_kpis", {}).get("dates", {})
    cur_date = state.get("target_month") or dates.get("cur", "")
    prv_date = dates.get("prv", "")

    os.makedirs(PLANS_DIR, exist_ok=True)
    # FormulaPlan 캐시 키 = 템플릿 + 정답지 (★ 데이터는 제외).
    # 식(KeySpec)은 구조적이며 period(cur/prv/mom)는 상대적이라 월이 바뀌어도 동일하다.
    # → raw_data만 바뀌면 캐시 히트로 식을 재사용하고, 엔진이 새 데이터로 값만 다시 계산한다.
    #   (새 정답지 없이도 새 달 output 산출 가능)
    p_hash = combined_hash(state["template_path"], state.get("answer_key_path"))
    cache_path = os.path.join(PLANS_DIR, f"formula_plan_{p_hash}.json")

    # ── 피드백 없고 캐시 있으면 즉시 로드 ──────────────────────────
    if not feedback and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            plan = KeySpecMapping(**data)
            if plan.specs:
                n = len(plan.specs)
                u = len(plan.unresolved)
                msg = (f"FormulaPlan 캐시 로드: {n}개 명세"
                       + (f" ({u}개 미해결)" if u else ""))
                print(f"[Planner] {msg}")
                return {
                    "key_spec_mapping": plan,
                    "pending_gate": "after_plan",
                    "messages": [AIMessage(content=msg, name="Planner")],
                }
        except Exception as e:
            print(f"[Planner] 캐시 로드 실패 ({e}) — 재생성")

    answer_key_path = state.get("answer_key_path")

    # ── 자아 진화: FailureReport 받으면 실패 key만 더 넓게 재합성 ──────────
    failure_reports = state.get("failure_reports") or []
    if (failure_reports and os.path.exists(cache_path)
            and answer_key_path and os.path.exists(answer_key_path)
            and cache_dir and os.path.isdir(cache_dir) and cur_date):
        try:
            with open(cache_path, encoding="utf-8") as f:
                prev = KeySpecMapping(**json.load(f))
            print(
                f"[Planner] 🧬 FailureReport {len(failure_reports)}건 수신 "
                f"— 실패 key 재합성(wider)"
            )
            evolved, replaced = _resynthesize_failed(
                prev, failure_reports, answer_key_path, cache_dir, cur_date, prv_date)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(evolved.model_dump(), f, ensure_ascii=False, indent=2)
            msg = f"FormulaPlan 자아 진화: 실패 {len(failure_reports)}건 중 {replaced}건 재합성"
            print(f"[Planner] {msg}")
            return {
                "key_spec_mapping": evolved,
                "pending_gate": "after_plan",
                "messages": [AIMessage(content=msg, name="Planner")],
            }
        except Exception as e:
            print(f"[Planner] 진화 실패 ({e}) — 전체 재생성으로 폴백")

    # ── 정답지 기반 결정론적 식 구성 (우선·LLM 없음) ────────────────────
    # 정답지 값을 target으로 raw_data에서 식을 역산한다. 못 맞추면 보고.
    if (not is_evolving and answer_key_path and os.path.exists(answer_key_path)
            and cache_dir and os.path.isdir(cache_dir) and cur_date):
        try:
            print("[Planner] 정답지 기반 식 구성 중 (deterministic fit)...")
            plan, report = _build_fit_plan(mapping, answer_key_path, cache_dir, cur_date, prv_date)
            report_str = _format_unfit_report(report)
            print(report_str)
            if plan.specs:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(plan.model_dump(), f, ensure_ascii=False, indent=2)
                # 정의 불가 키 리포트를 파일로도 남김
                rep_path = os.path.join(PLANS_DIR, f"unresolved_{p_hash}.json")
                with open(rep_path, "w", encoding="utf-8") as f:
                    json.dump({"reasons": report["unresolved_reasons"],
                               "conflicts": report["conflicts"]}, f, ensure_ascii=False, indent=2)
                # Thought→Plan→Action 결정 기록 (추적·human review용)
                dec_path = os.path.join(PLANS_DIR, f"decisions_{p_hash}.json")
                with open(dec_path, "w", encoding="utf-8") as f:
                    json.dump(report.get("decisions", []), f, ensure_ascii=False, indent=2)
                print(f"[Planner] 공식 결정 기록 저장: {os.path.basename(dec_path)} "
                      f"({len(report.get('decisions', []))}건, analysis/plan/action)")
                return {
                    "key_spec_mapping": plan,
                    "pending_gate": "after_plan",
                    "messages": [AIMessage(content=report_str, name="Planner")],
                }
            print("[Planner] fit 결과 0개 — LLM 폴백")
        except Exception as e:
            import traceback
            print(f"[Planner] fit 실패 ({e}) — LLM 폴백\n{traceback.format_exc()[:400]}")

    # ── LLM FormulaPlan 생성 (폴백: 정답지 없음 등) ─────────────────────
    schema_text = _schema_summary_for_planner(data_schema)
    key_line_map = _key_line_map(mapping)
    all_keys = list(key_line_map.keys())
    llm = _get_llm().with_structured_output(KeySpecMapping)

    def _chunks(keys: list[str]) -> list[list[str]]:
        return [keys[i:i + _BATCH_SIZE] for i in range(0, len(keys), _BATCH_SIZE)]

    if is_evolving:
        # ── 자아 진화: 실패한 key만 타겟 재생성 후 직전 plan에 병합 ──────
        fail_keys = sorted({
            i.value_key for i in ver_result.issues
            if i.root_cause in ("wrong_value", "missing_value") and i.value_key
        })
        batches = _chunks(fail_keys)
        print(
            f"[Planner] 🧬 자아 진화 — 실패 {len(fail_keys)}개 key 재생성 "
            f"({len(batches)}개 배치, 병렬 {_MAX_PARALLEL})"
        )
        def _evo_section(b):
            return _build_evolution_context(prev_plan, ver_result, only_keys=set(b))

        specs_new, unresolved_all = _run_batches(
            llm, batches, key_line_map, schema_text, cur_date, prv_date,
            extra_section_fn=_evo_section,
            instruction=(
                "위 실패한 key들의 KeySpec만 새로 작성하라. "
                "특정 불가 키는 unresolved에 추가."
            ),
            label="진화 배치",
        )
        # 병합: 직전 plan 유지 + 재생성된 key만 교체
        merged = {s.key: s for s in (prev_plan.specs if prev_plan else [])}
        for s in specs_new:
            merged[s.key] = s
        plan = KeySpecMapping(specs=list(merged.values()), unresolved=unresolved_all)
        print(f"[Planner] 진화 완료 → 총 {len(plan.specs)}개 명세, {len(unresolved_all)}개 미해결")

    else:
        # ── 최초 생성: 키를 배치로 나눠 병렬 호출 후 병합 (스케일 대응) ──────
        feedback_section = (
            f"\n\n## 이전 실행 피드백 (반드시 반영)\n{feedback}" if feedback else ""
        )
        batches = _chunks(all_keys)
        print(f"[Planner] FormulaPlan 생성 중 ({len(all_keys)}개 키 → "
              f"{len(batches)}개 배치, 병렬 {_MAX_PARALLEL})...")
        specs_all, unresolved_all = _run_batches(
            llm, batches, key_line_map, schema_text, cur_date, prv_date,
            extra_section_fn=lambda b: feedback_section,
            instruction="위 KPI 키에 대해 KeySpec을 작성하라. 특정 불가 키는 unresolved에 추가.",
            label="배치",
        )
        plan = KeySpecMapping(specs=specs_all, unresolved=unresolved_all)

    if not plan.specs:
        err = "Planner: 모든 배치 실패 — KeySpec 생성 0개"
        print(f"[Planner] ERROR: {err}")
        return {"errors": [err], "pending_gate": "after_plan"}

    # ── 캐시 저장 ──────────────────────────────────────────────────
    if plan.specs:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, ensure_ascii=False, indent=2)

    n = len(plan.specs)
    u = len(plan.unresolved)
    verb = "자아 진화" if is_evolving else "생성"
    msg = (f"FormulaPlan {verb}: {n}개 명세, {u}개 미해결"
           + (f" → {plan.unresolved[:3]}" if plan.unresolved else ""))
    print(f"[Planner] {msg}")

    return {
        "key_spec_mapping": plan,
        "pending_gate": "after_plan",
        "messages": [AIMessage(content=msg, name="Planner")],
    }
