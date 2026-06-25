"""excel_reader.py — Excel/CSV 원시 데이터 스키마 분석 + 샘플 집계."""
from __future__ import annotations
import os
import pandas as pd

from domain.config import FILE_KEYS, CATEGORICAL_COLUMNS


def load_file(path: str, nrows: int | None = None) -> pd.DataFrame:
    """nrows=None 이면 전체, 양수면 앞 nrows 행만 읽음 (스키마 분석용)."""
    if path.endswith(".csv"):
        return pd.read_csv(path, nrows=nrows)
    try:
        return pd.read_excel(path, engine="calamine", nrows=nrows)
    except Exception:
        return pd.read_excel(path, engine="openpyxl", nrows=nrows)


def _find(raw_dir: str, key: str) -> str | None:
    """raw_dir 에서 key 로 시작하는 첫 번째 파일 경로."""
    if not os.path.isdir(raw_dir):
        return None
    for f in sorted(os.listdir(raw_dir)):
        if f.startswith(key + ".") or f.startswith(key + " "):
            return os.path.join(raw_dir, f)
    return None


def get_all_schemas(raw_dir: str) -> dict:
    """raw_dir 의 모든 Excel/CSV 파일 스키마 + 샘플 KPI 반환."""
    schemas = []

    for _key, file_prefix in FILE_KEYS.items():
        path = _find(raw_dir, file_prefix)
        if not path:
            continue
        try:
            df = load_file(path, nrows=3000)
            info: dict = {
                "file": os.path.basename(path),
                "rows": len(df),
                "columns": list(df.columns),
                "dtypes": {c: str(df[c].dtype) for c in df.columns},
            }
            for col in CATEGORICAL_COLUMNS:
                if col in df.columns:
                    vals = sorted(df[col].dropna().unique().tolist())
                    info.setdefault("unique_values", {})[col] = vals[:30]
            schemas.append(info)
        except Exception as e:
            schemas.append({"file": file_prefix, "error": str(e)})

    # sample_kpis는 data_analyzer가 parquet 전체 기준으로 덮어씀
    # 여기선 빈 dict 반환 (하위 호환을 위해 키는 유지)
    return {
        "file_schemas": schemas,
        "sample_kpis": {},
    }
