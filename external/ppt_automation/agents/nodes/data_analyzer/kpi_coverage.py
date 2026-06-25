"""DataAnalyzer Skill 1 — KPI Coverage Validation 구현.

scan_coverage(): parquet 캐시를 스캔해 데이터셋별 DatasetCoverage 반환
validate_spec(): KeySpec의 컬럼이 coverage에 존재하는지 검증 → FAIL 메시지 또는 None
"""
from __future__ import annotations

import os

import pandas as pd

from agents.models import DatasetCoverage


def scan_coverage(cache_dir: str) -> dict[str, DatasetCoverage]:
    """parquet 캐시 디렉터리를 스캔해 데이터셋별 커버리지 반환.

    Rules (data_analyzer.md Skill 1):
    - 모든 컬럼명 lowercase normalize
    - row count 저장
    - 빈 DataFrame → warning 생성
    - 존재하지 않는 컬럼을 추정하지 않음
    """
    coverage: dict[str, DatasetCoverage] = {}
    for fname in sorted(os.listdir(cache_dir)):
        if not fname.endswith(".parquet"):
            continue
        key = fname[:-8]
        path = os.path.join(cache_dir, fname)
        try:
            df = pd.read_parquet(path)
            rows = len(df)
            columns = [c.lower() for c in df.columns]  # lowercase normalize
            warnings: list[str] = []

            if rows == 0:
                w = f"{key}: 빈 DataFrame (0행) — 이 데이터셋의 KPI는 모두 FAIL"
                warnings.append(w)
                print(f"  [Coverage] ⚠ {w}")

            coverage[key] = DatasetCoverage(
                dataset=key,
                rows=rows,
                columns=columns,
                warnings=warnings,
            )
            status = f"{rows:,}행 / {len(columns)}컬럼"
            print(f"  [Coverage] {key}: {status}" + (" ⚠ 빈 DataFrame" if rows == 0 else ""))
        except Exception as e:
            print(f"  [Coverage] {key} 스캔 실패: {e}")

    return coverage


def validate_spec(spec, coverage: dict[str, DatasetCoverage]) -> str | None:
    """KeySpec의 컬럼이 coverage에 존재하는지 검증.

    Rules:
    - df_key에 해당하는 parquet 없음 → FAIL
    - 빈 DataFrame → FAIL
    - value_col / denom_col / base_value_col 컬럼 없음 → FAIL
    - 존재하지 않는 컬럼명 추정 금지

    반환: FAIL 메시지(str) 또는 None(OK)
    """
    ds = coverage.get(spec.df_key)

    if ds is None:
        return f"FAIL [{spec.key}]: df_key={spec.df_key!r} parquet 없음"

    if ds.rows == 0:
        return f"FAIL [{spec.key}]: df_key={spec.df_key!r} 빈 DataFrame"

    cols = set(ds.columns)  # already lowercase

    if spec.value_col and spec.value_col.lower() not in cols:
        return (
            f"FAIL [{spec.key}]: df_key={spec.df_key!r} "
            f"value_col={spec.value_col!r} 컬럼 없음"
        )
    if spec.denom_col and spec.denom_col.lower() not in cols:
        return (
            f"FAIL [{spec.key}]: df_key={spec.df_key!r} "
            f"denom_col={spec.denom_col!r} 컬럼 없음"
        )
    if spec.base_value_col and spec.base_value_col.lower() not in cols:
        return (
            f"FAIL [{spec.key}]: df_key={spec.df_key!r} "
            f"base_value_col={spec.base_value_col!r} 컬럼 없음"
        )

    return None
