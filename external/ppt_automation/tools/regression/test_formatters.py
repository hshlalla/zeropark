"""formatters 순수 함수 테스트 — 집계값 → 표시 문자열 변환 규칙 고정.

표시 포맷이 바뀌면 PPT 의 모든 숫자 표기가 바뀌므로, 이 규칙을 회귀 테스트로 잠근다.
의존성 없음(순수 함수). 실행: python -m unittest discover -s tools/regression -t .
"""
import unittest

from core.predefined.formatters import (
    DASH, MAX_DECIMALS, _adaptive_decimals,
    fmt_kval, fmt_mom, fmt_mom_paren, fmt_pct, fmt_ratio, frac, mom,
)


class AdaptiveDecimalsTest(unittest.TestCase):
    def test_normal_value_keeps_decimals(self):
        self.assertEqual(_adaptive_decimals(1.5, 1), 1)

    def test_expands_until_significant(self):
        self.assertEqual(_adaptive_decimals(0.04, 1), 2)    # 0.0 → 0.04
        self.assertEqual(_adaptive_decimals(0.003, 1), 3)   # 0.0 → 0.003

    def test_exact_zero_keeps_base(self):
        self.assertEqual(_adaptive_decimals(0.0, 1), 1)

    def test_caps_at_max(self):
        self.assertEqual(_adaptive_decimals(0.00001, 1), MAX_DECIMALS)


class FmtPctTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(fmt_pct(76.8), "76.8%")
        self.assertEqual(fmt_pct(100.0), "100.0%")
        self.assertEqual(fmt_pct(0.0), "0.0%")

    def test_adaptive(self):
        self.assertEqual(fmt_pct(0.04), "0.04%")

    def test_none(self):
        self.assertEqual(fmt_pct(None), DASH)


class FmtMomTest(unittest.TestCase):
    def test_sign_always_shown(self):
        self.assertEqual(fmt_mom(0.9), "+0.9%p")
        self.assertEqual(fmt_mom(-0.1), "-0.1%p")
        self.assertEqual(fmt_mom(0.0), "+0.0%p")

    def test_adaptive(self):
        self.assertEqual(fmt_mom(0.03), "+0.03%p")
        self.assertEqual(fmt_mom(-0.03), "-0.03%p")

    def test_none(self):
        self.assertEqual(fmt_mom(None), DASH)


class FmtMomParenTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(fmt_mom_paren(0.9), "(+0.9%p)")
        self.assertEqual(fmt_mom_paren(-1.4), "(-1.4%p)")

    def test_none(self):
        self.assertEqual(fmt_mom_paren(None), f"({DASH})")


class FmtKvalTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(fmt_kval(25900), "25.9K")
        self.assertEqual(fmt_kval(84104), "84.1K")
        self.assertEqual(fmt_kval(0), "0.0K")

    def test_none(self):
        self.assertEqual(fmt_kval(None), DASH)


class FmtRatioTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(fmt_ratio(110, 100), "x1.10")
        self.assertEqual(fmt_ratio(85, 100), "x0.85")

    def test_invalid(self):
        self.assertEqual(fmt_ratio(None, 100), DASH)
        self.assertEqual(fmt_ratio(5, 0), DASH)
        self.assertEqual(fmt_ratio(5, None), DASH)


class MomTest(unittest.TestCase):
    def test_diff(self):
        self.assertEqual(mom(5, 3), 2)
        self.assertAlmostEqual(mom(76.8, 75.8), 1.0)
        self.assertEqual(mom(0, 0), 0)

    def test_none_propagates(self):
        self.assertIsNone(mom(None, 3))
        self.assertIsNone(mom(3, None))


class FracTest(unittest.TestCase):
    def test_scale(self):
        self.assertEqual(frac(50), 0.5)
        self.assertEqual(frac(0), 0.0)

    def test_none(self):
        self.assertIsNone(frac(None))


if __name__ == "__main__":
    unittest.main()
