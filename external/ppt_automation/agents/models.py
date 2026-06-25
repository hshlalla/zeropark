"""models.py — PPT 채우기 파이프라인 전체 Pydantic 스키마."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Manager: Gate 통과 기록 ───────────────────────────────────────────────────

class GateResult(BaseModel):
    """Manager 게이트 하나의 통과/실패 기록."""
    gate: str          # "after_data" | "after_mapping" | "after_plan" | "after_calc" | "after_fill" | "after_verify"
    passed: bool
    details: str       # 통과 기준과 실제 측정값
    route_to: str      # 다음 노드 이름 또는 "__end__"
    retry_count: int   # 이 게이트 실행 시점의 전역 retry_count


# ── Reader Skill 2: KPI Discovery Completeness ───────────────────────────────

class PlaceholderLocation(BaseModel):
    """Reader Skill 2 — 탐지된 숫자 placeholder 위치."""
    slide_idx: int
    shape_num: Optional[int] = None
    shape_name: str = ""
    shape_type: Literal["table", "text", "chart"] = "table"
    row: int = 0
    col: int = 0
    placeholder_text: str
    format_hint: str = ""   # pct / mom / kval / ratio / chart


class DiscoveryResult(BaseModel):
    """Reader Skill 2 — Mapping Completeness Check 결과."""
    # 전체 (소형 table + text — 차트/대형 table 제외)
    total_numeric_placeholders: int
    mapped_placeholders: int
    coverage: float                           # mapped / total
    # 구분별
    table_total: int = 0
    table_mapped: int = 0
    text_total: int = 0
    text_mapped: int = 0
    chart_total: int = 0                      # 미구현 (항상 0 매핑)
    # 미매핑 목록
    unmapped: list[PlaceholderLocation] = Field(default_factory=list)
    passed: bool                              # coverage >= 0.95


# ── DataAnalyzer Skill 1: KPI Coverage Validation ────────────────────────────

class DatasetCoverage(BaseModel):
    """단일 parquet 데이터셋의 컬럼 커버리지 정보."""
    dataset: str
    rows: int
    columns: list[str]         # lowercase normalize 된 컬럼명 목록
    warnings: list[str] = Field(default_factory=list)


# ── Calculator 명세 (LLM이 1회 생성 → 고정 엔진이 매번 계산) ────────────────

class KeySpec(BaseModel):
    """단일 KPI 키의 계산 명세 (FormulaPlan의 항목).

    계산 공식: sum(value_col) / sum(denom_col) * scale
    period에 따라 날짜 필터가 다르게 적용됨.
    """
    key: str
    df_key: str              # FILE_KEYS 내부 키 ("bv", "rv", "st" 등) → {df_key}.parquet
    value_col: str           # 분자 컬럼 (sum)
    denom_col: str = ""      # 분모 컬럼 (sum). 빈 문자열이면 순수 합산 (÷ 생략)
    filters: dict[str, str] = Field(default_factory=dict)
    # {컬럼명: 값} — 값이 "global" 또는 빈 문자열이면 해당 컬럼 필터 생략
    exclude_values: dict[str, list[str]] = Field(default_factory=dict)
    # {컬럼명: [제외값, ...]} — 예: {"platform": ["Claude"]}
    period: Literal["cur", "prv", "mom", "ratio", "diff"] = "cur"
    # cur   → cur_date 기준 집계
    # prv   → prv_date 기준 집계
    # mom   → cur 집계 − prv 집계 (MoM 차이)
    # ratio → cur 집계 ÷ prv 집계 (배수, x0.85 표시용)
    # diff  → main_filters 집계 − base_filters 집계 (vs. 비교값)
    scale: float = 100.0     # 결과 배율: 퍼센트 → 100, raw/K단위/ratio → 1
    base_filters: dict[str, str] = Field(default_factory=dict)
    # period="diff" 전용: 차감할 기준 필터 (예: global Samsung BV)
    base_exclude_values: dict[str, list[str]] = Field(default_factory=dict)
    base_value_col: str = ""
    # period="diff" 전용: base에서 다른 컬럼 사용 시 지정
    note: str = ""           # 사람이 읽는 설명 (예: "Samsung BV 현월 글로벌 %")


class KeySpecMapping(BaseModel):
    """Planner 출력: SlideMapping unique_keys 전체의 계산 명세 집합 (FormulaPlan).

    Planner가 LLM으로 생성 → Calculator가 이를 기반으로 Python 코드 생성.
    unresolved: 명세를 세울 수 없었던 키 목록 (데이터 불명, 컬럼 불명 등).
    """
    specs: list[KeySpec] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)   # 명세 미완성 키

    def get(self, key: str) -> Optional[KeySpec]:
        for s in self.specs:
            if s.key == key:
                return s
        return None

    @property
    def is_complete(self) -> bool:
        return len(self.unresolved) == 0


# ── Reader 출력 ───────────────────────────────────────────────────────────────

class ShapeTarget(BaseModel):
    """Reader가 생성하는 PPT 좌표 + KPI 키 매핑 (셀 단위)."""
    slide_idx: int
    shape_num: int
    shape_id: int | None = None   # XML id 속성 — 이름 변경에 무관한 안정적 식별자
    shape_name: str = ""
    shape_type: Literal["table", "text", "chart"] = "table"
    # table → 표 셀 (row/col 사용)
    # text  → 차트 위 텍스트 도형 (row=0, col=0)
    # chart → 차트 도형 (향후 시계열 데이터 채우기 예정)
    row: int
    col: int
    value_key: str        # Calculator가 출력할 키 이름 (e.g. "bv_samsung_global_cur")
    format_type: Literal["pct", "mom", "raw", "kval", "text", "ratio"] = "pct"
    context: str = ""     # 어떤 지표인지 사람이 읽는 설명
    # Smart Block 메타 — 어느 block에 속하는지 (디버깅·에이전트 라우팅 용)
    block_type: str | None = None   # "KPI_CARD" | "TABLE_SECTION" | "CHART" | "LABEL"
    block_label: str | None = None  # KPI_CARD의 segment 레이블 (예: "Support")


class ChartTarget(BaseModel):
    """차트 한 계열(series)의 매핑 + 채우기 명세.

    차트는 표/텍스트와 달리 (카테고리 × 계열) 구조라 별도 타깃으로 표현한다.
    category_kind:
      "time"     → 카테고리가 월(시계열). 각 카테고리 = 해당 월의 메트릭.
      "category" → 카테고리가 세그먼트(플랫폼/intent/채널 등). 각 카테고리 = 그 값으로 필터한 메트릭.
    """
    slide_idx: int
    shape_num: int
    shape_id: int | None = None
    categories: list[str] = Field(default_factory=list)   # x축 라벨
    category_kind: Literal["time", "category"] = "category"
    category_dim: str = ""        # category_kind="category"일 때 데이터 차원 컬럼 (예: platform)
    series_name: str = ""
    series_idx: int = 0
    value_key: str = ""           # 식별용 key
    # ── 해소(fit)된 계산 명세 ────────────────────────────────────────
    df_key: str = ""
    value_col: str = ""
    denom_col: str = ""
    filters: dict[str, str] = Field(default_factory=dict)  # 고정 필터(company/country 등)
    scale: float = 1.0
    period: str = "cur"           # time 차트의 기본 기간(보통 카테고리가 월이라 미사용)
    resolved: bool = False        # fit 성공 여부
    reason: str = ""              # 미해소 사유 (보고용)


class SlideMapping(BaseModel):
    """Reader의 최종 출력: 슬라이드 전체 좌표+키 매핑 가이드."""
    targets: list[ShapeTarget] = Field(default_factory=list)
    chart_targets: list[ChartTarget] = Field(default_factory=list)

    @property
    def unique_keys(self) -> list[str]:
        return sorted(set(t.value_key for t in self.targets))

    def get_targets_for_key(self, key: str) -> list[ShapeTarget]:
        return [t for t in self.targets if t.value_key == key]


# ── Calculator 출력 ───────────────────────────────────────────────────────────

class CalculatedValue(BaseModel):
    """단일 KPI 계산 결과."""
    key: str
    raw_value: Optional[float] = None
    formatted_value: str = "-"
    formula_note: str = ""   # 계산식 메모 (디버깅용)


class CalculationResult(BaseModel):
    """Calculator 전체 출력: key → CalculatedValue 매핑."""
    values: dict[str, CalculatedValue] = Field(default_factory=dict)
    chart_series: dict[str, list] = Field(default_factory=dict)
    # {value_key: [v0, v1, ...]} — 차트 계열별 카테고리 값 목록 (None = 데이터 없음)

    def get(self, key: str) -> Optional[CalculatedValue]:
        return self.values.get(key)

    def get_formatted(self, key: str) -> str:
        cv = self.values.get(key)
        return cv.formatted_value if cv else "-"

    def missing_keys(self, mapping: SlideMapping) -> list[str]:
        return [k for k in mapping.unique_keys if k not in self.values]


# ── Verifier 출력 ─────────────────────────────────────────────────────────────

class VerificationIssue(BaseModel):
    """검증 실패 셀 상세 + 원인 분류."""
    slide_idx: int
    shape_num: int
    row: int
    col: int
    value_key: str = ""
    expected: str
    actual: str
    root_cause: Literal[
        "wrong_value",    # 계산값 자체가 틀림 → Calculator로 라우팅
        "wrong_cell",     # 올바른 값이 엉뚱한 셀에 들어감 → Filler로 라우팅
        "format_error",   # 값은 맞지만 포맷이 다름 → Filler로 라우팅
        "missing_value",  # 값이 채워지지 않음 → Filler로 라우팅
        "unknown",
    ] = "unknown"
    suggestion: str = ""  # 다음 에이전트에게 줄 구체적 힌트

    def label(self) -> str:
        return f"slide={self.slide_idx} shape={self.shape_num} [{self.row},{self.col}]"


class FailureReport(BaseModel):
    """검증 실패 1건의 구조화 리포트 — Verifier → Planner 자아 진화 입력.

    Planner는 이걸 받아 '실패한 key만' 다시 공식 후보를 생성한다.
    """
    key: str
    expected: str
    actual: str
    suspected_causes: list[str] = Field(default_factory=list)
    # 예: ["wrong numerator", "wrong filter", "wrong period", "wrong scale", "wrong denominator"]
    next_action: str = "regenerate_formula_candidates"


class VerificationResult(BaseModel):
    """검증 결과 + 조건부 라우팅 피드백."""
    passed: bool
    total_checked: int = 0
    ok_count: int = 0
    issues: list[VerificationIssue] = Field(default_factory=list)
    # 조건부 엣지: "calculator" → KPI 재계산, "filler" → PPT 재채우기, "end" → 종료
    route_to: Literal["calculator", "filler", "end"] = "end"
    feedback: str = ""   # 다음 에이전트에게 줄 구체적 피드백 메시지

    def summary(self) -> str:
        pct = self.ok_count / self.total_checked * 100 if self.total_checked else 0
        status = "✓ 통과" if self.passed else f"✗ 실패 → {self.route_to}"
        return f"{status} | {self.ok_count}/{self.total_checked} ({pct:.0f}%) | 이슈 {len(self.issues)}개"

    def calc_issues(self) -> list[VerificationIssue]:
        return [i for i in self.issues if i.root_cause == "wrong_value"]

    def filler_issues(self) -> list[VerificationIssue]:
        return [i for i in self.issues if i.root_cause in ("wrong_cell", "format_error", "missing_value")]


# ── 레거시 (호환성) ────────────────────────────────────────────────────────────

class ValidationIssue(BaseModel):
    """구형 검증 이슈 (FillReport 호환용)."""
    slide_idx: int
    shape_num: int
    row: int
    col: int
    expected: str
    actual: str

    def label(self) -> str:
        return f"slide={self.slide_idx} shape={self.shape_num} [{self.row},{self.col}]"


class CellFill(BaseModel):
    row: int
    col: int
    expected: Optional[str] = None
    actual: Optional[str] = None
    status: Literal["pending", "ok", "mismatch"] = "pending"


class ShapeFill(BaseModel):
    shape_num: int
    shape_name: str = ""
    shape_type: str = "table"
    cells: list[CellFill] = Field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for c in self.cells if c.status == "ok")

    @property
    def mismatch_count(self) -> int:
        return sum(1 for c in self.cells if c.status == "mismatch")


class SlideFill(BaseModel):
    slide_idx: int
    shapes: list[ShapeFill] = Field(default_factory=list)

    @property
    def total_cells(self) -> int:
        return sum(len(s.cells) for s in self.shapes)

    @property
    def ok_count(self) -> int:
        return sum(s.ok_count for s in self.shapes)


class FillReport(BaseModel):
    slides: list[SlideFill] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def total_cells(self) -> int:
        return sum(s.total_cells for s in self.slides)

    @property
    def ok_count(self) -> int:
        return sum(s.ok_count for s in self.slides)

    @property
    def mismatch_count(self) -> int:
        return len(self.issues)

    def summary(self) -> str:
        total = self.total_cells
        ok = self.ok_count
        bad = self.mismatch_count
        pct = ok / total * 100 if total else 0
        return f"전체 {total}셀 | 일치 {ok} ({pct:.0f}%) | 불일치 {bad}"
