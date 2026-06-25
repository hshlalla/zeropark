"""formatters.py — KPI 숫자 → 표시 문자열 변환 순수 함수.

회귀 테스트(tools/regression/test_formatters.py)에서 직접 임포트됨.
계산기(calculator.py)도 이 모듈을 사용해 일관성을 보장한다.
"""
from __future__ import annotations

DASH = "-"
MAX_DECIMALS = 4


def _adaptive_decimals(value: float, base: int) -> int:
    """소수점 자릿수를 최소한으로 늘려 유효 숫자가 보이도록 한다.

    round(v, base) == 0.0 이면 자릿수를 늘리고, MAX_DECIMALS에서 멈춘다.
    v == 0.0 이면 base 그대로 유지.
    """
    if value == 0.0:
        return base
    d = base
    while d < MAX_DECIMALS and round(value, d) == 0.0:
        d += 1
    return d


def fmt_pct(value: float | None, decimals: int = 1) -> str:
    """퍼센트 포맷. 예: 76.8 → '76.8%', 0.04 → '0.04%'"""
    if value is None:
        return DASH
    v = float(value)
    d = _adaptive_decimals(abs(v), decimals)
    return f"{v:.{d}f}%"


def fmt_mom(value: float | None, decimals: int = 1) -> str:
    """MoM 변화량 포맷. 예: 0.9 → '+0.9%p', -0.1 → '-0.1%p'"""
    if value is None:
        return DASH
    v = float(value)
    d = _adaptive_decimals(abs(v), decimals)
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{d}f}%p"


def fmt_mom_paren(value: float | None, decimals: int = 1) -> str:
    """괄호 MoM 포맷. 예: 0.9 → '(+0.9%p)', -1.4 → '(-1.4%p)', None → '(-)'"""
    return f"({fmt_mom(value, decimals)})"


def fmt_kval(value: float | None) -> str:
    """K 단위 포맷. 예: 25900 → '25.9K'"""
    if value is None:
        return DASH
    return f"{float(value) / 1000:.1f}K"


def fmt_ratio(num: float | None, denom: float | None) -> str:
    """두 값의 비율 포맷. 예: fmt_ratio(110, 100) → 'x1.10'"""
    if num is None or denom is None:
        return DASH
    try:
        d = float(denom)
        if d == 0:
            return DASH
        return f"x{float(num) / d:.2f}"
    except (TypeError, ValueError):
        return DASH


def fmt_ratio_val(value: float | None) -> str:
    """이미 계산된 비율 값 포맷. 예: fmt_ratio_val(0.85) → 'x0.85'

    kpi_engine의 period="ratio" 결과(cur÷prv)를 직접 받아 표시한다.
    """
    if value is None:
        return DASH
    try:
        return f"x{float(value):.2f}"
    except (TypeError, ValueError):
        return DASH


def mom(cur: float | None, prv: float | None) -> float | None:
    """MoM 차이값 계산. None 전파."""
    if cur is None or prv is None:
        return None
    return float(cur) - float(prv)


def frac(value: float | None) -> float | None:
    """퍼센트 → 분수 변환. 예: frac(50) → 0.5"""
    if value is None:
        return None
    return float(value) / 100.0
