"""metric_resolver.py — value_key를 표준 metric_id 구조로 정규화.

예) "bv_samsung_us_cur"
  → MetricId(metric_family="bv", entity="samsung", country="US",
             period="cur", comparison=None, extras=[])
   "bv_samsung_total_us_vs_coa"
  → MetricId(family="bv", entity="samsung", country="US",
             period="diff", comparison="vs_coa", extras=["total"])
   "rv_owned_global_cur"
  → MetricId(family="rv", entity=None, country="global", period="cur", extras=["owned"])

도메인 무관 파서 — 국가 집합만 domain.config에서 받는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.config import KNOWN_COUNTRIES

_ENTITIES = {"samsung", "apple"}
_PERIODS = {"cur", "prv", "mom", "ratio", "share", "diff"}
_COUNTRY_SET = {c.lower() for c in KNOWN_COUNTRIES} | {"global"}


@dataclass
class MetricId:
    raw_key: str
    metric_family: str = ""
    entity: str | None = None
    country: str = "global"
    period: str = "cur"
    comparison: str | None = None   # "vs_coa" | "vs_global" | None
    extras: list[str] = field(default_factory=list)  # owned/total/aimode/rank1/platform 등


def resolve(value_key: str) -> MetricId:
    """value_key를 MetricId로 파싱."""
    toks = [t for t in value_key.lower().split("_") if t]
    if not toks:
        return MetricId(raw_key=value_key)

    family = toks[0]
    body = toks[1:]

    comparison = None
    period = "cur"

    # 꼬리에서 comparison/period 추출
    # vs_coa / vs_global (두 토큰)
    if len(body) >= 2 and body[-2] == "vs" and body[-1] in ("coa", "global"):
        comparison = f"vs_{body[-1]}"
        period = "diff"
        body = body[:-2]
    elif body and body[-1] in _PERIODS:
        period = body[-1]
        body = body[:-1]

    entity = None
    country = "global"
    extras: list[str] = []
    for t in body:
        if t in _ENTITIES:
            entity = t
        elif t in _COUNTRY_SET:
            country = t.upper() if t != "global" else "global"
        else:
            extras.append(t)

    return MetricId(
        raw_key=value_key, metric_family=family, entity=entity,
        country=country, period=period, comparison=comparison, extras=extras,
    )


_ENTITY_COMPANY = {"samsung": "Samsung", "apple": "Apple"}


def entity_filters(mid: MetricId) -> dict[str, str]:
    """MetricId → 기본 필터(company/country). 세그먼트(extras)는 포함 안 함."""
    f: dict[str, str] = {}
    if mid.entity in _ENTITY_COMPANY:
        f["company"] = _ENTITY_COMPANY[mid.entity]
    if mid.country and mid.country != "global":
        f["country"] = mid.country
    return f
