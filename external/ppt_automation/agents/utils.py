"""공유 유틸리티: 파일 해시, 경로 상수."""
from __future__ import annotations

import hashlib
import os

# 프로젝트 루트 (agents/ 의 상위)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# cache/ : 런타임 캐시 (scans JSON, memory.db) — 삭제해도 자동 재생성
GENERATED_DIR = os.path.join(_ROOT, "cache")

# core/agent_generated/ : 에이전트가 템플릿/데이터를 "보고 저작"한 산출물.
#   - 템플릿 특화 로직 모듈(metric_resolver/formula_critic/formula_fit/chart_fill)
#   - 아래 런타임 산출물: 어디에 뭘 넣을지(mappings) · 계산식(plans) · 계산 코드(calculators)
AGENT_GENERATED_DIR = os.path.join(_ROOT, "core", "agent_generated")

# 에이전트가 생성하는 파일 종류별 하위 폴더 (모두 agent_generated/ 아래)
# mapping_*.json (어디에 뭘 넣을지)
MAPPINGS_DIR    = os.path.join(AGENT_GENERATED_DIR, "mappings")
# kpi_calculator_*.py (LLM fallback 코드)
CALCULATORS_DIR = os.path.join(AGENT_GENERATED_DIR, "calculators")
# formulas_*.py (도출된 계산식 고정 코드)
FORMULAS_DIR    = os.path.join(AGENT_GENERATED_DIR, "formulas")


# Anthropic API 키 조회 우선순위 (앞에 있는 환경변수부터 사용)
_API_KEY_ENV_ORDER = ("CX_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", "Score_Claude_API_KEY")


def get_anthropic_api_key() -> str | None:
    """Anthropic API 키를 환경변수에서 우선순위 순으로 조회."""
    for name in _API_KEY_ENV_ORDER:
        v = os.environ.get(name)
        if v:
            return v
    return None


PLANS_DIR       = os.path.join(AGENT_GENERATED_DIR, "plans")       # formula_plan_*.json (계산식)


def _hash_file(path: str, h: "hashlib._Hash") -> None:
    """파일 첫 1MB를 해시에 추가."""
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))


def template_hash(template_path: str) -> str:
    """템플릿 파일 MD5 해시 (12자리 hex)."""
    h = hashlib.md5()
    _hash_file(template_path, h)
    return h.hexdigest()[:12]


def combined_hash(template_path: str, answer_key_path: str | None = None) -> str:
    """템플릿 + 정답지 복합 MD5 해시 (12자리 hex).

    SlideMapping(mapping_*.json) 캐시 키로 사용.
    answer_key가 바뀌면 해시가 달라져 자동 캐시 무효화.
    """
    h = hashlib.md5()
    _hash_file(template_path, h)
    if answer_key_path and os.path.exists(answer_key_path):
        _hash_file(answer_key_path, h)
    return h.hexdigest()[:12]


def spec_cache_hash(
    template_path: str,
    answer_key_path: str | None = None,
    data_cache_dir: str | None = None,
) -> str:
    """템플릿 + 정답지 + parquet mtime 복합 MD5 해시 (12자리 hex).

    kpi_calculator_{hash}.py 캐시 키로 사용.
    raw 데이터가 재빌드돼 parquet mtime이 바뀌면 해시가 달라져 자동 캐시 무효화.
    """
    h = hashlib.md5()
    _hash_file(template_path, h)
    if answer_key_path and os.path.exists(answer_key_path):
        _hash_file(answer_key_path, h)
    if data_cache_dir and os.path.isdir(data_cache_dir):
        for fname in sorted(os.listdir(data_cache_dir)):
            if fname.endswith(".parquet"):
                mtime = os.path.getmtime(os.path.join(data_cache_dir, fname))
                h.update(fname.encode())
                h.update(str(mtime).encode())
    return h.hexdigest()[:12]


_NODES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes")


def load_skills(agent_name: str) -> str:
    """agents/nodes/{agent_name}/{agent_name}-skills.md를 읽어 반환. 없으면 빈 문자열."""
    path = os.path.join(_NODES_DIR, agent_name, f"{agent_name}-skills.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


# ── 모든 LLM 에이전트에 강제 주입되는 가드레일 (눈대중 금지/도구 강제) ────────
TOOL_ENFORCEMENT_GUARDRAIL = """\
# ⛔ 절대 원칙 — 눈대중 금지 / 도구 강제 (모든 응답에 우선 적용)

## 금지 (하면 실패)
- 숫자를 **근사·추측**하지 말 것 ("대략", "약 80%" 등 추정 금지)
- 데이터에 없는 **컬럼명을 상상**하지 말 것 (스키마에 실재하는 컬럼만 사용)
- PPT에서 **보이지 않는 문맥을 추정**하지 말 것 (스캔 결과에 있는 것만 근거로)
- **계산 없이 값을 확정**하지 말 것

## 필수 (반드시 이 도구·근거를 사용)
- **pptx_scanner 결과**로 PPT 구조/값을 파악 (직접 상상 금지)
- **data_coverage**로 데이터·컬럼 존재를 확인한 뒤 사용
- 값은 **formula_engine으로 계산**해서만 산출
- 계산값은 **answer_key와 오차 비교**로 검증
- 채택 근거(계산값·오차·후보)를 **evidence로 기록**

검증·계산되지 않은 값은 출력하지 말고 **미해결(unresolved) + 사유**로 남겨라.
"""


def load_contract(agent_name: str) -> str:
    """agents/nodes/{agent_name}/{agent_name}-contract.md 반환.

    ★ 모든 LLM 에이전트 system 프롬프트에 가드레일(눈대중 금지/도구 강제)을 자동 prepend.
    """
    path = os.path.join(_NODES_DIR, agent_name, f"{agent_name}-contract.md")
    body = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            body = f.read().strip()
    return f"{TOOL_ENFORCEMENT_GUARDRAIL}\n\n---\n\n{body}" if body else TOOL_ENFORCEMENT_GUARDRAIL
