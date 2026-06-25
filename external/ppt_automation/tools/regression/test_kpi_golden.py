"""KPI 골든(characterization) 테스트 — '숫자가 바뀌면 실패'하는 회귀 안전망.

parquet 캐시에서 집계를 **재계산**해, 슬라이드에 들어가는 대표 KPI 값을
현재 확정값에 고정한다. 집계/계산 로직이 바뀌어 값이 달라지면 즉시 실패한다.
LLM 인사이트(비결정적)는 대상이 아니다 — 오직 숫자.

parquet(.data_cache/)가 없거나 RUN_GOLDEN 미설정이면 자동 skip:
    RUN_GOLDEN=1 python -m unittest discover -s tools/regression -t .
"""
import os
import unittest

# ── 프로젝트 루트를 sys.path에 추가 ──────────────────────────────────────────
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agents.nodes.data_analyzer import _cache_dir_for as _cdf
_RAW_DATA_DIR = os.path.join(_ROOT, "raw_data")
_CACHE_DIR = _cdf(_RAW_DATA_DIR)


def r1(v):
    return None if v is None else round(v, 1)


@unittest.skipUnless(os.environ.get("RUN_GOLDEN"),
                     "느린 골든 테스트 — RUN_GOLDEN=1 로 실행")
class KpiGoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bv_path = os.path.join(_CACHE_DIR, "bv.parquet")
        if not os.path.exists(bv_path):
            raise unittest.SkipTest(
                "parquet 캐시 없음 — build_report.py 를 먼저 실행해 .data_cache/ 를 생성하세요"
            )
        try:
            import pandas as pd
            df = pd.read_parquet(bv_path, columns=["date"])
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            dates = sorted(df["date"].dropna().unique().tolist())
        except Exception as e:
            raise unittest.SkipTest(f"parquet 로드 실패: {e}")

        cls.CUR = dates[-1]
        cls.PRV = dates[-2] if len(dates) >= 2 else dates[-1]

        from core.kpi_engine import _load, _agg
        from agents.models import KeySpec
        cls._load = staticmethod(_load)
        cls._agg  = staticmethod(_agg)
        cls.KeySpec = KeySpec

    def _bv(self, company: str, *, platform: str = "", exclude_claude: bool = False,
             cur: bool = True) -> float | None:
        filters = {"company": company}
        if platform:
            filters["platform"] = platform
        exc = {"platform": ["Claude"]} if exclude_claude else {}
        spec = self.KeySpec(
            key="_", df_key="bv",
            value_col="galaxy_mention", denom_col="denominator",
            filters=filters, exclude_values=exc,
            period="cur", scale=100,
        )
        df = self._load(_CACHE_DIR, "bv")
        return self._agg(df, spec, self.CUR if cur else self.PRV)

    # ── 기준월 자동 감지 ────────────────────────────────────────────────────
    def test_detected_dates(self):
        self.assertEqual(self.CUR, "2026-04-26")
        self.assertEqual(self.PRV, "2026-03-29")

    # ── Global KPI (정답지 기준) ────────────────────────────────────────────
    def test_global_brand_visibility(self):
        self.assertEqual(r1(self._bv("Samsung", exclude_claude=True)), 76.8)
        self.assertEqual(r1(self._bv("Samsung", exclude_claude=True, cur=False)), 75.8)

    def test_global_apple_bv(self):
        spec = self.KeySpec(
            key="_", df_key="bv",
            value_col="iphone_mention", denom_col="denominator",
            filters={"company": "Apple"}, exclude_values={"platform": ["Claude"]},
            period="cur", scale=100,
        )
        df = self._load(_CACHE_DIR, "bv")
        self.assertEqual(r1(self._agg(df, spec, self.CUR)), 69.7)

    def test_global_brand_visibility_chatgpt(self):
        self.assertEqual(r1(self._bv("Samsung", platform="ChatGPT")), r1(
            self._bv("Samsung", platform="ChatGPT")))  # smoke: no exception

    # ── 날짜 정규화 유틸 ────────────────────────────────────────────────────
    def test_month_normalization(self):
        """_normalize_month 가 다양한 형식을 올바르게 처리하는지 확인."""
        from agents.nodes.data_analyzer import _normalize_month
        available = [self.PRV, self.CUR]
        # YYYY-MM-DD 그대로
        self.assertEqual(_normalize_month(self.CUR, available), self.CUR)
        # YYYY-MM → 해당 월 최신 날짜
        self.assertEqual(_normalize_month(self.CUR[:7], available), self.CUR)
        # 월 숫자만 → 해당 월 최신 날짜
        month_num = str(int(self.CUR[5:7]))
        self.assertEqual(_normalize_month(month_num, available), self.CUR)
        # 없는 월 → None
        self.assertIsNone(_normalize_month("99", available))


if __name__ == "__main__":
    unittest.main()
