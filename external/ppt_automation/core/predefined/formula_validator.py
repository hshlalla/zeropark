"""Formula Validator — 후보 공식을 raw_data로 '계산해 검증'하는 역할.

단일 책임: 후보를 실제 데이터로 계산해 정답지/전월/타국가 값과 비교, 오차 산출.
생성/판단은 안 한다.
"""
from __future__ import annotations

import pandas as pd


class FormulaValidator:
    def compute(self, candidate: dict, df: pd.DataFrame, filters: dict, date: str) -> float | None:
        """후보를 (필터·날짜)로 계산. df는 '_dnorm' 정규화돼 있다고 가정."""
        sub = df
        if date and "_dnorm" in sub.columns:
            sub = sub[sub["_dnorm"] == date]
        for c, v in filters.items():
            if c in sub.columns:
                sub = sub[sub[c].astype(str) == str(v)]
        num = candidate["num"]
        if num not in sub.columns or len(sub) == 0:
            return None
        n = pd.to_numeric(sub[num], errors="coerce").sum()
        denom = candidate["denom"]
        if denom:
            if denom not in sub.columns:
                return None
            d = pd.to_numeric(sub[denom], errors="coerce").sum()
            val = float(n) / float(d) if d else None
        else:
            val = float(n)
        return val * candidate["scale"] if val is not None else None

    def compute_on(self, candidate: dict, sub: pd.DataFrame) -> float | None:
        """이미 (엔티티·날짜) 슬라이스된 sub에서 계산. 성능용 빠른 경로."""
        num = candidate["num"]
        if num not in sub.columns or len(sub) == 0:
            return None
        n = pd.to_numeric(sub[num], errors="coerce").sum()
        denom = candidate["denom"]
        if denom:
            if denom not in sub.columns:
                return None
            d = pd.to_numeric(sub[denom], errors="coerce").sum()
            val = float(n) / float(d) if d else None
        else:
            val = float(n)
        return val * candidate["scale"] if val is not None else None

    def score_on(self, candidate: dict, sub: pd.DataFrame, target: float) -> float:
        """단일 target에 대한 상대오차 (사전 슬라이스). 계산 불가면 inf."""
        v = self.compute_on(candidate, sub)
        if v is None:
            return float("inf")
        return abs(v - target) / (abs(target) or 1)

    def validate(self, candidate: dict, df: pd.DataFrame, refs: list[tuple]) -> tuple[float, int]:
        """refs = [(filters, date, target), ...] 전체 교차검증.

        반환: (평균 상대오차, 검증한 참조 수). 하나라도 계산 불가면 (inf, 0).
        """
        errs = []
        for filters, date, target in refs:
            if target in (None, 0):
                continue
            val = self.compute(candidate, df, filters, date)
            if val is None:
                return float("inf"), 0
            errs.append(abs(val - target) / (abs(target) or 1))
        if not errs:
            return float("inf"), 0
        return sum(errs) / len(errs), len(errs)
