"""metric_catalog.py — metric_family별 공식 정의(카탈로그).

각 family가 "어떻게 계산되는지"를 한 곳에서 명시한다. Planner는 이 카탈로그를 보고
MetricId → KeySpec을 만든다. 새 지표는 여기에 항목/핸들러만 추가하면 된다.

strategy:
  "ratio"       : sum(num)/sum(denom) × scale (entity/country 필터) — 정의 명확한 family
  "fit"         : 정답지 값을 target으로 식 역산 (컬럼이 난해한 family: rv/rs)
  "ranking"     : top-N 도메인 랭킹 — 전용 핸들러 필요 (현재 미구현 → 보고)
  "chart"       : 차트 — core/chart_fill.py가 처리 (KeySpec 대상 아님)
  "unsupported" : 데이터/정의 없음 → 보고
"""
from __future__ import annotations

from agents.models import KeySpec
from core.predefined.metric_resolver import MetricId

# ── family별 정의 ─────────────────────────────────────────────────────────────
CATALOG: dict[str, dict] = {
    "bv": {
        "strategy": "ratio", "dataset": "bv",
        "num_by_entity": {"samsung": "galaxy_mention", "apple": "iphone_mention"},
        "num_default": "galaxy_mention",
        "denom": "denominator", "scale": 100.0,
    },
    "sentiment": {
        "strategy": "ratio", "dataset": "st",
        "num_default": "positive_sentiment", "denom": "denominator", "scale": 100.0,
    },
    # st_* 접두사: sentiment와 동일 데이터셋/공식
    "st": {
        "strategy": "ratio", "dataset": "st",
        "num_default": "positive_sentiment", "denom": "denominator", "scale": 100.0,
    },
    # owned_* 접두사: rv 데이터셋의 Owned Total 컬럼
    "owned": {
        "strategy": "ratio", "dataset": "rv",
        "num_default": "Owned__Owned_Total__Owned_Total",
        "denom": "Denominator", "scale": 100.0,
    },
    # rv/rs: extras가 알려진 세그먼트면 직접 ratio 처리, 아니면 정답지 기반 fit
    "rv": {"strategy": "fit", "dataset": "rv"},
    "rs": {"strategy": "fit", "dataset": "rs"},
    # 전용 핸들러 필요/미정의
    "traffic":    {"strategy": "unsupported", "reason": "전용 traffic 공식 미정의(데이터셋 없음)"},
    "domain":     {"strategy": "ranking", "reason": "도메인 랭킹(top-N) 핸들러 필요"},
    "topdomain":  {"strategy": "ranking", "reason": "도메인 랭킹(top-N) 핸들러 필요"},
    "sourcetype": {"strategy": "unsupported", "reason": "sourcetype 공식/데이터 매핑 미정의"},
    "chart":      {"strategy": "chart", "reason": "차트는 chart_fill 모듈이 처리"},
}

_ENTITY_COMPANY = {"samsung": "Samsung", "apple": "Apple"}

# value_key의 extra 토큰 → (데이터 컬럼, 값) 필터. 알려진 세그먼트만.
_EXTRA_FILTERS: dict[str, tuple[str, str]] = {
    "aimode": ("platform", "Google AI Mode"),
    "aioverview": ("platform", "Google AI Overview"),
    "chatgpt": ("platform", "ChatGPT"),
    "gemini": ("platform", "Gemini"),
    "perplexity": ("platform", "Perplexity"),
    "claude": ("platform", "Claude"),
}

# rv extra 토큰(단일 또는 '_' 조합) → rv 데이터셋 컬럼명.
# 매핑이 있으면 fit 없이 직접 ratio KeySpec 생성.
_RV_SEGMENT_COLUMNS: dict[str, str] = {
    # 채널 총계
    "owned":           "Owned__Owned_Total__Owned_Total",
    "external":        "External__External_Total__External_Total",
    "forum":           "External__Forum_Total__Forum_Total",
    "social":          "External__Social_Total__Social_Total",
    "media":           "External__Media_Total__Media_Total",
    "partner":         "External__Partnercom_Total__Partnercom_Total",
    "partnercom":      "External__Partnercom_Total__Partnercom_Total",
    "wiki":            "External__Wiki_Total__Wiki_Total",
    "wikipedia":       "External__Wiki__Wiki",
    "blog":            "External__Blog_Review_Total__Blog_Review_Total",
    "blogreview":      "External__Blog_Review_Total__Blog_Review_Total",
    "blog_review":     "External__Blog_Review_Total__Blog_Review_Total",
    "otherbrand":      "External__Other_Tech_Hardware_Brand_Total__Other_Tech_Hardware_Brand_Total",
    "otherbrands":     "External__Other_Tech_Hardware_Brand_Total__Other_Tech_Hardware_Brand_Total",
    "other":           "External__Other_Tech_Hardware_Brand_Total__Other_Tech_Hardware_Brand_Total",
    "others":          "External__Others_Total__Others_Total",
    "retailer":        "External__Partnercom__Retailer",
    "softwaresaas":    (
        "External__Software_Saas_Productivity_Total__Software_Saas_Productivity_Total"
    ),
    "refurbretailer":  "External__Refurbished_Retailer_Total__Refurbished_Retailer_Total",
    "relatedproduct":  (
        "External__Smartphone_Related_Product_and_Service_Total"
        "__Smartphone_Related_Product_and_Service_Total"
    ),
    # Owned 하위
    "support":         "Owned__Support__Support",
    "pr":              "Owned__PR__Newsroom",
    "community":       "Owned__Community__Community",
    "dotcom":          "Owned__Dotcom_Support_Total__Dotcom_Support_Total",
    "news":            "External__Media__Media_PR",
    "mktpdp":          "Owned__Dotcom__MKT_PDP",
    "buy":             "Owned__Dotcom__Buy",
    "buyingguide":     "Owned__Dotcom__Buying_Guide",
    "galaxyai":        "Owned__Dotcom__Galaxy_AI",
    # compound extras (mid.extras를 '_'로 조인한 키)
    "channel_forum":        "External__Forum_Total__Forum_Total",
    "channel_social":       "External__Social_Total__Social_Total",
    "channel_media":        "External__Media_Total__Media_Total",
    "channel_owned":        "Owned__Owned_Total__Owned_Total",
    "channel_partner":      "External__Partnercom_Total__Partnercom_Total",
    "channel_otherbrand":   (
        "External__Other_Tech_Hardware_Brand_Total__Other_Tech_Hardware_Brand_Total"
    ),
    "channel_wiki":         "External__Wiki_Total__Wiki_Total",
    "seg_forum":            "External__Forum_Total__Forum_Total",
    "seg_social":           "External__Social_Total__Social_Total",
    "seg_media":            "External__Media_Total__Media_Total",
    "seg_news":             "External__Media_Total__Media_Total",
    "seg_blog_review":      "External__Blog_Review_Total__Blog_Review_Total",
    "seg_wiki":             "External__Wiki_Total__Wiki_Total",
    "seg_video":            "External__Social__YouTube",
    "seg_community":        "Owned__Community__Community",
    "seg_owned_dotcom":     "Owned__Dotcom_Only_Total__Dotcom_Only_Total",
    "seg_owned_support":    "Owned__Support__Support",
    "seg_owned_newsroom":   "Owned__PR__Newsroom",
    "seg_owned_app":        "Owned__Dotcom__Apps",
    "seg_owned_community":  "Owned__Community__Community",
    "seg_owned_other":      "Owned__Others__Others",
}


def _base_filters(mid: MetricId) -> dict[str, str]:
    f: dict[str, str] = {}
    if mid.entity in _ENTITY_COMPANY:
        f["company"] = _ENTITY_COMPANY[mid.entity]
    if mid.country and mid.country != "global":
        f["country"] = mid.country
    for ex in mid.extras:
        if ex in _EXTRA_FILTERS:
            col, val = _EXTRA_FILTERS[ex]
            f[col] = val
    return f


def _numerator(spec_def: dict, mid: MetricId) -> str:
    by = spec_def.get("num_by_entity")
    if by and mid.entity in by:
        return by[mid.entity]
    return spec_def.get("num_default", "")


def _rv_segment_keyspec(mid: MetricId) -> KeySpec | None:
    """rv family + 알려진 세그먼트 extras → ratio KeySpec (fit 불필요).

    extras를 '_'로 조인해 _RV_SEGMENT_COLUMNS에서 컬럼을 찾는다.
    단일 토큰도 조인 결과와 동일하게 처리된다.
    """
    extra_key = "_".join(mid.extras)
    col = _RV_SEGMENT_COLUMNS.get(extra_key)
    if col is None:
        return None
    filters = _base_filters(mid)
    # extras 기반 필터는 여기선 불필요 (컬럼 자체가 세그먼트를 특정)
    return KeySpec(
        key=mid.raw_key, df_key="rv",
        value_col=col, denom_col="Denominator",
        filters=filters, period=mid.period, scale=100.0,
    )


def _ratio_keyspec(spec_def: dict, mid: MetricId) -> KeySpec:
    """ratio family → KeySpec (comparison이면 diff)."""
    num = _numerator(spec_def, mid)
    denom = spec_def.get("denom", "")
    scale = spec_def.get("scale", 1.0)
    df_key = spec_def["dataset"]
    filters = _base_filters(mid)

    if mid.comparison == "vs_global":
        # 기준 = 같은 지표의 global (country 필터 제거)
        base = dict(filters)
        base.pop("country", None)
        return KeySpec(key=mid.raw_key, df_key=df_key, value_col=num, denom_col=denom,
                       filters=filters, base_filters=base, period="diff", scale=scale,
                       note="vs_global diff")
    if mid.comparison == "vs_coa":
        # 기준 = 경쟁사(Apple) 동일 위치
        base = dict(filters)
        base["company"] = "Apple"
        return KeySpec(key=mid.raw_key, df_key=df_key, value_col=num, denom_col=denom,
                       filters=filters, base_filters=base, base_value_col="iphone_mention",
                       period="diff", scale=scale, note="vs_coa diff")
    return KeySpec(key=mid.raw_key, df_key=df_key, value_col=num, denom_col=denom,
                   filters=filters, period=mid.period, scale=scale)


def get_strategy(mid: MetricId) -> dict:
    """family의 카탈로그 정의 반환 (없으면 unsupported)."""
    return CATALOG.get(mid.metric_family,
                       {"strategy": "unsupported",
                        "reason": f"카탈로그에 family '{mid.metric_family}' 없음"})


def build_keyspec(mid: MetricId) -> tuple[KeySpec | None, str, dict]:
    """MetricId → (KeySpec|None, 사유, 전략정의).

    strategy="ratio" → 명시적 KeySpec 즉시 반환.
    strategy="fit"   → None 반환하되 전략정의에 dataset 포함 (Planner가 fit 수행).
    그 외(ranking/chart/unsupported) → None + 사유.
    """
    sdef = get_strategy(mid)
    strat = sdef["strategy"]
    if strat == "ratio":
        return _ratio_keyspec(sdef, mid), "", sdef
    if strat == "fit":
        # rv extras가 알려진 세그먼트면 fit 없이 직접 처리
        if sdef.get("dataset") == "rv" and mid.extras:
            ks = _rv_segment_keyspec(mid)
            if ks:
                return ks, "", sdef
        return None, "fit_required", sdef
    return None, sdef.get("reason", strat), sdef
