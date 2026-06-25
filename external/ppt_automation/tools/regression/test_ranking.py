"""도메인 경쟁식 순위(_top_domains_prev) 테스트 — 합성 DataFrame.

동점=같은 등수, 다음 등수는 동점 수만큼 건너뜀(18,18,20). raw 데이터 불필요.
"""
import unittest

import pandas as pd

from core.ranking import _top_domains_prev


def _df(rows):
    """rows: [(domain, count, company, date, country)] → df_dom 스키마."""
    return pd.DataFrame(
        [{"domain_excl_protocol": d, "domain_count": c, "company": co,
          "date": dt, "country": ct} for d, c, co, dt, ct in rows]
    )


class TopDomainsPrevRankTest(unittest.TestCase):
    def test_competition_rank_with_ties(self):
        df = _df([
            ("a.com", 10, "Samsung", "P", "US"),
            ("b.com", 8, "Samsung", "P", "US"),
            ("c.com", 8, "Samsung", "P", "US"),   # b 와 동점
            ("d.com", 5, "Samsung", "P", "US"),   # 동점 2개 건너뛴 4위
        ])
        ranks = _top_domains_prev(df, "P", "US")
        self.assertEqual(ranks["a.com"], 1)
        self.assertEqual(ranks["b.com"], 2)
        self.assertEqual(ranks["c.com"], 2)
        self.assertEqual(ranks["d.com"], 4)      # 3 이 아니라 4 (경쟁식)

    def test_sums_same_domain_rows(self):
        df = _df([
            ("a.com", 4, "Samsung", "P", "US"),
            ("a.com", 6, "Samsung", "P", "US"),   # 합산 10
            ("b.com", 7, "Samsung", "P", "US"),
        ])
        ranks = _top_domains_prev(df, "P", "US")
        self.assertEqual(ranks["a.com"], 1)       # 10 > 7
        self.assertEqual(ranks["b.com"], 2)

    def test_filters_company_date_country(self):
        df = _df([
            ("a.com", 10, "Samsung", "P", "US"),
            ("z.com", 99, "Apple", "P", "US"),     # 타사 제외
            ("y.com", 99, "Samsung", "Q", "US"),   # 타월 제외
            ("x.com", 99, "Samsung", "P", "UK"),   # 타국 제외
        ])
        ranks = _top_domains_prev(df, "P", "US")
        self.assertEqual(set(ranks), {"a.com"})
        self.assertEqual(ranks["a.com"], 1)


if __name__ == "__main__":
    unittest.main()
