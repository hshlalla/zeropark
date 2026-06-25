"""build_report.py — MX GEO 리포트 빌드 CLI.

사용법:
  ./run.sh                               # 기본 실행 (자동 감지)
  ./run.sh --month 2026-04               # 특정 월
  ./run.sh --template template/새파일.pptx
  ./run.sh --answer-key answer_key/정답.pptx
  ./run.sh --regenerate                  # 코드 강제 재생성
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_template() -> str | None:
    cands = sorted(glob.glob(os.path.join(BASE_DIR, "template", "*_base_template*.pptx")))
    return cands[-1] if cands else None


def _find_answer_key() -> str | None:
    cands = sorted(glob.glob(os.path.join(BASE_DIR, "answer_key", "*.pptx")))
    return cands[-1] if cands else None


def main() -> None:
    parser = argparse.ArgumentParser(description="MX GEO Report 자동 빌드")
    parser.add_argument("--template", default=None,
                        help="PPT 템플릿 경로 (생략 시 template/*_base_template*.pptx 자동 탐지)")
    parser.add_argument("--answer-key", default=None, dest="answer_key",
                        help="정답지 PPT 경로 (생략 시 answer_key/*.pptx 자동 탐지)")
    parser.add_argument("--raw-data", default="raw_data", dest="raw_data",
                        help="원시 데이터 폴더 (기본: raw_data/)")
    parser.add_argument("--output", default=None,
                        help="출력 PPT 경로 (생략 시 output/filled_YYYYMMDD.pptx)")
    parser.add_argument("--month", default=None,
                        help="기준월 (예: 2026-04). 생략 시 데이터 최신 월 자동 감지")
    parser.add_argument("--regenerate", action="store_true",
                        help="기존 생성 코드를 무시하고 LLM으로 재생성")
    args = parser.parse_args()

    # ── 경로 결정 ────────────────────────────────────────────────────────────
    template_path = args.template or _find_template()
    if not template_path or not os.path.exists(template_path):
        print("[ERROR] 템플릿 파일을 찾을 수 없습니다.")
        print("  → template/ 폴더에 '_base_template' 이름을 포함한 .pptx 파일을 넣어주세요.")
        sys.exit(1)

    answer_key_path = args.answer_key or _find_answer_key()
    raw_data_dir = os.path.join(BASE_DIR, args.raw_data)

    print(f"· 템플릿  : {os.path.basename(template_path)}")
    print(f"· 정답지  : {os.path.basename(answer_key_path) if answer_key_path else '없음 (집계 재계산으로 검증)'}")
    print(f"· 데이터  : {raw_data_dir}")

    # ── 재생성 플래그: 해당 템플릿+정답지의 모든 캐시 파일 삭제 ──────────────
    if args.regenerate:
        from agents.utils import template_hash, MAPPINGS_DIR, CALCULATORS_DIR, PLANS_DIR
        t_hash = template_hash(template_path)
        deleted = []
        # SlideMapping 캐시 (템플릿 해시 기반 — 정답지와 무관)
        mapping_path = os.path.join(MAPPINGS_DIR, f"mapping_{t_hash}.json")
        if os.path.exists(mapping_path):
            os.remove(mapping_path)
            deleted.append(os.path.basename(mapping_path))
        # FormulaPlan 캐시
        for f in glob.glob(os.path.join(PLANS_DIR, "formula_plan_*.json")):
            os.remove(f)
            deleted.append(os.path.basename(f))
        # KPI 계산 코드
        for f in glob.glob(os.path.join(CALCULATORS_DIR, "kpi_calculator_*.py")):
            os.remove(f)
            deleted.append(os.path.basename(f))
        if deleted:
            print(f"· 캐시 삭제: {', '.join(deleted)} → LLM 재생성")
        else:
            print(f"· 삭제할 캐시 없음 (template hash={t_hash})")

    # ── LangGraph 파이프라인 실행 ────────────────────────────────────────────
    from agents.graph import get_app

    initial_state = {
        # ── 입력 ──────────────────────────────────────────────────────
        "template_path": template_path,
        "answer_key_path": answer_key_path,
        "raw_data_dir": raw_data_dir,
        "output_path": args.output,
        "target_month": args.month,
        # ── 분석 결과 ─────────────────────────────────────────────────
        "data_schema": None,
        "data_cache_dir": None,
        "template_schema": None,
        # ── Reader 출력 ───────────────────────────────────────────────
        "slide_mapping": None,
        # ── Planner 출력 (FormulaPlan) ────────────────────────────────
        "key_spec_mapping": None,
        # ── Calculator 출력 ───────────────────────────────────────────
        "calculation_result": None,
        # ── Filler 출력 ───────────────────────────────────────────────
        "execution_output_path": None,
        # ── Calculator 코드 캐시 경로 ─────────────────────────────────
        "kpi_code_path": None,
        # ── Verifier 출력 ─────────────────────────────────────────────
        "verification_result": None,
        "validation_issues": None,
        "fill_report": None,
        # ── Manager Gate 제어 ─────────────────────────────────────────
        "pending_gate": None,
        # ── 재시도 제어 ───────────────────────────────────────────────
        "retry_count": 0,
        "retry_feedback": None,
        # ── 레거시 호환 ───────────────────────────────────────────────
        "generated_code_path": None,
        # ── 차트 채우기 통계 ──────────────────────────────────────────
        "chart_counts": None,
        # ── Annotated reducer 필드 ────────────────────────────────────
        "messages": [],
        "errors": [],
        "gate_results": [],
    }

    print("\n─── 멀티 에이전트 파이프라인 시작 ───")
    app = get_app()
    # 노드 수 계산: 기본 1회 통과 ≈ 12스텝(노드+manage 교차).
    # 자아 진화 1사이클 ≈ 8스텝, HARD_ITERATION_LIMIT(7)회까지 = +56스텝.
    # 국소 소프트캡 재시도 여유 포함해 넉넉히 120으로 제한 (하드 가드가 먼저 멈춤).
    config = {"recursion_limit": 120}
    final = app.invoke(initial_state, config=config)

    # ── 결과 출력 ────────────────────────────────────────────────────────────
    print("\n─── 결과 ───")
    for msg in final.get("messages", []):
        print(f"  [{getattr(msg, 'name', '?')}] {msg.content}")

    # ── Human-in-the-loop 하드 리밋 배너 (최우선 표시) ──────────────────────
    hitl_signals = [e for e in (final.get("errors") or []) if "HUMAN-IN-THE-LOOP" in e]
    if hitl_signals:
        print("\n" + "=" * 70)
        print("⛔ 사람 검토 필요 (HUMAN-IN-THE-LOOP)")
        print("=" * 70)
        for s in hitl_signals:
            print(f"  {s}")
        print("  → 자동 파이프라인이 하드 리밋에서 멈췄습니다. "
              "수식 명세(FormulaPlan)와 매핑을 수동 점검하세요.")
        print("=" * 70)

    if final.get("errors"):
        print("\n[오류]")
        for e in final["errors"]:
            print(f"  • {e}")

    # Verifier 결과 출력
    ver = final.get("verification_result")
    if ver:
        print(f"\n[검증 결과] {ver.summary()}")
        if ver.issues:
            print(f"  피드백: {ver.feedback[:200]}")
            for iss in ver.issues[:5]:
                print(f"  • {iss.label()} [{iss.root_cause}] expected={iss.expected!r} actual={iss.actual!r}")
            if len(ver.issues) > 5:
                print(f"  ... 외 {len(ver.issues)-5}개")
    elif final.get("fill_report"):
        fr = final["fill_report"]
        print(f"\n[채우기 상태] {fr.summary()}")

    out = final.get("execution_output_path") or final.get("output_path")
    if out:
        print(f"\n· 출력 파일: {out}")
    if final.get("kpi_code_path"):
        print(f"· KPI 코드 : {final['kpi_code_path']}")

    # 공유 메모리 현황 (누적 학습)
    try:
        from core.predefined.shared_memory import get_memory
        print(f"· 공유 메모리: {get_memory().stats()}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
