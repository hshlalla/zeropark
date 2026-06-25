"""Formula Synthesizer — 공식 후보를 여러 개 '생성'만 하는 역할.

단일 책임: (분자/분모/scale) 후보 목록을 만든다. 계산/검증/판단은 안 한다.
key 토큰과 컬럼명 겹침으로 분자 후보를 우선순위화한다.
"""
from __future__ import annotations

import re
import pandas as pd

from core.predefined.metric_resolver import MetricId

_DENOM_RE = re.compile(r"denom|denominator|total|base", re.I)


class FormulaSynthesizer:
    def candidates(self, mid: MetricId, df: pd.DataFrame, df_key: str, fmt: str,
                   top: int = 8) -> list[dict]:
        """후보 = {df_key, num, denom, scale} 목록. top=분자 후보 수(진화 시 확대)."""
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        denom_cols = [c for c in df.columns if _DENOM_RE.search(c)]
        ktoks = set(re.split(r"[_\s]+", mid.raw_key.lower()))
        nums = sorted(
            [c for c in numeric if c not in denom_cols],
            key=lambda c: -len(ktoks & set(re.split(r"[_\s]+", c.lower()))),
        )[:top]
        if fmt in ("pct", "mom"):
            scales = [100.0]
        elif fmt == "kval":
            scales = [0.001, 1.0]
        else:
            scales = [1.0, 100.0]
        out = []
        for num in nums:
            for denom in [""] + denom_cols:
                for sc in scales:
                    out.append({"df_key": df_key, "num": num, "denom": denom, "scale": sc})
        return out
