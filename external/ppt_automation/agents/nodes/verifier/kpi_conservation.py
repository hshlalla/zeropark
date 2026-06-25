"""Pipeline Skill 0 — End-to-End KPI Conservation 구현.

check_conservation()      : 전 단계 KPI 수 일치 검증 → PIPELINE FAIL 여부
print_conservation_report(): 단계별 수치 테이블 출력
"""
from __future__ import annotations

# 단계 정의 (순서 고정)
_STAGES: list[tuple[str, str]] = [
    ("reader",      "Reader"),
    ("calculator",  "Calculator"),
    ("filler_in",   "Filler In"),
    ("filler_out",  "Filler Out"),
]


def check_conservation(kpi_counts: dict) -> tuple[bool, list[str]]:
    """파이프라인 KPI 보존 불변식 검증.

    진짜 불변식 = "매핑된 셀(reader)이 채우기에서 손실되지 않는다":
      · filler_in  == reader  (Filler가 모든 매핑 target을 처리)
      · filler_out == filler_in (쓰기 실패로 셀을 잃지 않음)

    calculator < reader 는 정상이다 — 일부 key는 명세 미해결이라 값이 None이며,
    이는 Filler가 "-"로 채우고 Verifier가 감지해 Planner 자아 진화가 메운다.
    따라서 calculator 부족은 FAIL이 아니다 (단, reader 초과는 손상 → FAIL).

    반환: (passed, 오류 메시지 목록)
    """
    reader = kpi_counts.get("reader")
    calc = kpi_counts.get("calculator")
    fin = kpi_counts.get("filler_in")
    fout = kpi_counts.get("filler_out")

    errors: list[str] = []

    # 채우기 손실 = 진짜 보존 위반
    if reader is not None and fin is not None and fin != reader:
        errors.append(f"PIPELINE FAIL: filler_in={fin} ≠ reader={reader} (매핑 셀 손실 {reader - fin}개)")
    if fin is not None and fout is not None and fout != fin:
        errors.append(f"PIPELINE FAIL: filler_out={fout} ≠ filler_in={fin} (쓰기 실패 {fin - fout}개)")

    # calculator가 reader를 초과하면 손상 (불가능한 상황)
    if reader is not None and calc is not None and calc > reader:
        errors.append(f"PIPELINE FAIL: calculator={calc} > reader={reader} (KPI 중복/손상)")

    return len(errors) == 0, errors


def print_conservation_report(kpi_counts: dict) -> None:
    """KPI Conservation Report를 콘솔에 출력."""
    print("[Pipeline] ══ KPI Conservation Report ══")
    for key, label in _STAGES:
        if key in kpi_counts:
            print(f"  {label:<15} {kpi_counts[key]}")

    ok, errors = check_conservation(kpi_counts)
    all_present = all(key in kpi_counts for key, _ in _STAGES)
    if all_present or errors:
        print("  ──────────────────────────")
        if ok:
            print("  PASS ✓")
        else:
            for err in errors:
                print(f"  ⚠ {err}")
