"""Formula Critic — 숫자는 맞아도 '의미가 이상한' 공식을 제거하는 역할.

단일 책임: 후보 공식의 의미적 타당성만 판단한다. (계산/검증은 안 함)
예: Samsung KPI인데 분자에 iphone_mention → 탈락.
"""
from __future__ import annotations

from core.predefined.metric_resolver import MetricId


class FormulaCritic:
    def judge(self, candidate: dict, mid: MetricId) -> tuple[bool, str]:
        """후보가 의미적으로 타당한지 (passes, reason)."""
        num = (candidate.get("num") or "").lower()

        # 엔티티 ↔ 분자 일관성
        if mid.entity == "samsung" and "iphone" in num:
            return False, "Samsung KPI인데 분자가 iphone_mention"
        if mid.entity == "apple" and "galaxy" in num:
            return False, "Apple KPI인데 분자가 galaxy_mention"

        # 분자가 분모류 컬럼이면 의심 (denominator를 값으로 쓰는 건 보통 틀림)
        if num in ("denominator", "denom", "base"):
            return False, "분자에 분모성 컬럼 사용"

        return True, "ok"

    def passes(self, candidate: dict, mid: MetricId) -> bool:
        """검증 전 값싼 의미 선필터."""
        ok, _ = self.judge(candidate, mid)
        return ok

    def review(self, best: dict, mid: MetricId, evidence: dict) -> tuple[bool, str, float]:
        """검증 후 evidence(계산값·오차·대안 후보)까지 보고 최종 판단.

        evidence = {"value": float, "error": float, "alternatives": [(cand, err), ...]}
        반환: (통과, 사유, confidence_penalty[0~1, 곱셈])
        """
        # 1) 의미 일관성
        ok, reason = self.judge(best, mid)
        if not ok:
            return False, reason, 1.0

        err = evidence.get("error", 0.0)
        alts = evidence.get("alternatives", [])

        # 2) 모호성: 분자 컬럼이 다른 대안이 거의 같은 오차로 맞으면 우연 일치 위험
        for c, e in alts:
            if c.get("num") != best.get("num") and abs(e - err) < 0.01 and self.passes(c, mid):
                return True, f"모호(대안 {c['num']}도 유사 오차 {e:.0%}) — confidence 감점", 0.7

        # 3) 분자가 key 의미와 전혀 무관한데 오차만 0에 가까우면 의심 (약한 신호)
        return True, "ok", 1.0
