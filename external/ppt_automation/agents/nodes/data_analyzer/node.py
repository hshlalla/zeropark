"""Agent — Excel 원시 데이터 스키마 분석 + parquet 캐시 생성.

날짜(cur_date/prv_date) 감지는 parquet 전체 데이터 기준.
스키마 분석(컬럼명, 유니크값)은 3000행 샘플 사용.
"""
from __future__ import annotations

import hashlib
import os
import re

import pandas as pd
from core.predefined.excel_reader import _find, get_all_schemas, load_file
from domain.config import DATE_PRIORITY, FILE_KEYS
from langchain_core.messages import AIMessage

from agents.state import AgentState
from agents.utils import load_skills

from .kpi_coverage import scan_coverage

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cache_dir_for(raw_data_dir: str) -> str:
    """raw_data_dir 절대경로 해시로 격리된 parquet 캐시 디렉터리 경로 반환.

    다른 raw_data_dir → 다른 캐시 디렉터리 → 교차 오염 방지.
    """
    abs_path = os.path.abspath(raw_data_dir)
    h = hashlib.md5(abs_path.encode()).hexdigest()[:12]
    return os.path.join(_ROOT, ".data_cache", h)


def _parquet_is_fresh(parquet_path: str, src_path: str) -> bool:
    """parquet이 소스 파일보다 최신이면 True (mtime 비교)."""
    if not os.path.exists(parquet_path):
        return False
    return os.path.getmtime(src_path) <= os.path.getmtime(parquet_path)


def _build_parquet_cache(raw_data_dir: str) -> str:
    """Excel 원시 파일을 parquet으로 변환·캐시.

    raw_data_dir 절대경로 해시 기반 서브디렉터리를 사용해
    서로 다른 데이터셋이 동일 캐시를 공유하는 문제를 방지한다.
    소스 파일 mtime이 parquet보다 새로우면 자동 재빌드.
    """
    cache_dir = _cache_dir_for(raw_data_dir)
    os.makedirs(cache_dir, exist_ok=True)
    for key, file_prefix in FILE_KEYS.items():
        parquet_path = os.path.join(cache_dir, f"{key}.parquet")
        src_path = _find(raw_data_dir, file_prefix)
        if not src_path:
            continue
        if _parquet_is_fresh(parquet_path, src_path):
            continue  # 소스보다 캐시가 최신 → 재사용
        print(f"  [캐시] {file_prefix} → {key}.parquet (신규/갱신)...")
        try:
            df = load_file(src_path)
            df.to_parquet(parquet_path, index=False)
        except Exception as e:
            print(f"  [경고] {key} parquet 생성 실패: {e}")
    return cache_dir


def _all_dates(cache_dir: str) -> list[str]:
    """parquet에서 전체 날짜 목록을 정렬·중복제거해 반환 (columnar read)."""
    for key in DATE_PRIORITY:
        path = os.path.join(cache_dir, f"{key}.parquet")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_parquet(path, columns=["date"])
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            return sorted(df["date"].dropna().unique().tolist())
        except Exception:
            continue
    return []


def _normalize_month(raw: str, available_dates: list[str]) -> str | None:
    """--month 입력을 YYYY-MM-DD로 정규화.

    수용 형식:
      "2026-04-26"  전체 날짜 — 그대로 반환
      "2026-04"     연-월  — available_dates에서 해당 월 최신 날짜
      "4" / "04"    월만   — 해당 월 최신 날짜 (연도 무관, 가장 최근 우선)
    """
    raw = raw.strip()
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    # YYYY-MM
    if re.match(r"^\d{4}-\d{2}$", raw):
        matches = [d for d in available_dates if d.startswith(raw)]
        return max(matches) if matches else None
    # M 또는 MM
    if re.match(r"^\d{1,2}$", raw):
        month_num = int(raw)
        matches = [d for d in available_dates if int(d[5:7]) == month_num]
        return max(matches) if matches else None
    return None


_SKILLS = load_skills("data_analyzer")  # agents/skills/data_analyzer.md


def analyze_data(state: AgentState) -> dict:
    """raw_data/ Excel 파일을 분석해 data_schema + parquet 캐시를 생성.

    Skills: data_analyzer.md (Skill 1 — KPI Coverage Validation)
    반환: data_schema / data_cache_dir / data_coverage (override), messages (append)
    """
    raw_data_dir = state["raw_data_dir"]
    print(f"[DataAnalyzer] Excel 스키마 분석: {raw_data_dir}")
    if _SKILLS:
        print(f"[DataAnalyzer] Skills 로드됨: data_analyzer.md ({len(_SKILLS.splitlines())}줄)")

    try:
        # ── 1. 스키마 (3000행 샘플 — 컬럼명/유니크값 파악용) ──────────
        data_schema = get_all_schemas(raw_data_dir)
        n_files = len(data_schema["file_schemas"])

        # ── 2. parquet 캐시 (전체 데이터) ─────────────────────────────
        print("[DataAnalyzer] parquet 캐시 생성 중 (전체 데이터)...")
        cache_dir = _build_parquet_cache(raw_data_dir)
        cached_files = [f for f in os.listdir(cache_dir) if f.endswith(".parquet")]

        # ── Skill 1: KPI Coverage Validation ──────────────────────────
        print("[DataAnalyzer] [Skill 1] KPI Coverage Validation 실행 중...")
        coverage = scan_coverage(cache_dir)
        coverage_warnings = [w for ds in coverage.values() for w in ds.warnings]
        if coverage_warnings:
            for w in coverage_warnings:
                print(f"[DataAnalyzer] [Skill 1] ⚠ {w}")
        else:
            print(f"[DataAnalyzer] [Skill 1] {len(coverage)}개 데이터셋 커버리지 확인 완료")

        # ── 3. 날짜 감지 (parquet 전체 기준, 샘플 아님) ───────────────
        all_dates = _all_dates(cache_dir)
        if all_dates:
            dates = {
                "cur": all_dates[-1],
                "prv": all_dates[-2] if len(all_dates) >= 2 else all_dates[-1],
            }
        else:
            dates = data_schema.get("sample_kpis", {}).get("dates", {})
            print("[DataAnalyzer] 경고: parquet에서 날짜 감지 실패 — 샘플 기반 폴백")

        # ── 4. --month 정규화 (입력 형식 통일) ───────────────────────
        target_month_raw = state.get("target_month")
        normalized_month: str | None = None
        if target_month_raw and all_dates:
            normalized = _normalize_month(str(target_month_raw), all_dates)
            if normalized:
                # cur = 지정 월의 마지막 날짜, prv = 그 이전 다른 월의 마지막 날짜
                cur_ym = normalized[:7]
                earlier = [d for d in all_dates if d < normalized and d[:7] != cur_ym]
                prv = max(earlier) if earlier else normalized
                dates = {"cur": normalized, "prv": prv}
                normalized_month = normalized
                print(
                    f"[DataAnalyzer] --month 정규화: {target_month_raw!r}"
                    f" → {normalized} (prv={prv})"
                )
            else:
                print(
                    f"[DataAnalyzer] 경고: --month {target_month_raw!r}"
                    " 에 맞는 날짜 없음 — 최신월 사용"
                )

        # sample_kpis는 날짜만 유지 (샘플 KPI 값은 부정확하므로 제거)
        data_schema["sample_kpis"] = {"dates": dates}

        msg = (f"데이터 분석 완료: {n_files}개 파일 | "
               f"기준월={dates.get('cur', '?')} / 전월={dates.get('prv', '?')} | "
               f"parquet 캐시 {len(cached_files)}개")
        print(f"[DataAnalyzer] {msg}")

        updates: dict = {
            "data_schema": data_schema,
            "data_cache_dir": cache_dir,
            "data_coverage": {k: v.model_dump() for k, v in coverage.items()},
            "pending_gate": "after_data",
            "messages": [AIMessage(content=msg, name="DataAnalyzer")],
        }
        if normalized_month:
            updates["target_month"] = normalized_month
        return updates

    except Exception as e:
        err = f"데이터 분석 실패: {e}"
        print(f"[DataAnalyzer] ERROR: {err}")
        return {"errors": [err]}
