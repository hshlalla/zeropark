"""formula_codegen.py — 도출된 계산식(KeySpecMapping)을 재사용 가능한 .py 코드로 출력.

목적: "매 실행마다 다시 도출/계산"하지 않고, 한 번 도출한 계산식을 코드 파일로 고정한다.
이후 실행은 재도출 없이 그 파일을 import해 재사용한다(raw_data가 바뀌어도 같은 식으로 새 값).

이 모듈은 범용 직렬화기다 — 도메인/템플릿 지식이 없다. 어떤 KeySpecMapping이 와도
동일한 규칙으로 KeySpec 리터럴을 코드로 렌더링한다. 결과 .py는 core/agent_generated/에 쓰인다.
직렬화는 LLM이 아니라 결정론적 렌더링이라 안정적이다.
"""
from __future__ import annotations

import importlib.util
import os
from types import ModuleType

# 생성 파일 위치(core/agent_generated/formulas/)에서 프로젝트 루트까지 거슬러 올라갈 깊이.
# .../core/agent_generated/formulas/formulas_x.py → dirname 4회 = 루트
_ROOT_UP = 4


def _keyspec_literal(spec) -> str:
    """KeySpec 하나를 `KeySpec(...)` 코드 리터럴로. 기본값 필드는 생략해 가독성↑.

    핵심 식 필드(key/df_key/value_col/period/scale)는 항상 표기, 나머지는 비기본값만.
    값은 repr()로 직렬화 → str/dict/float 모두 유효한 파이썬 코드가 된다.
    """
    parts = [
        f"key={spec.key!r}",
        f"df_key={spec.df_key!r}",
        f"value_col={spec.value_col!r}",
    ]
    if spec.denom_col:
        parts.append(f"denom_col={spec.denom_col!r}")
    if spec.filters:
        parts.append(f"filters={dict(spec.filters)!r}")
    if spec.exclude_values:
        parts.append(f"exclude_values={dict(spec.exclude_values)!r}")
    parts.append(f"period={spec.period!r}")
    parts.append(f"scale={float(spec.scale)!r}")
    if spec.base_filters:
        parts.append(f"base_filters={dict(spec.base_filters)!r}")
    if spec.base_exclude_values:
        parts.append(f"base_exclude_values={dict(spec.base_exclude_values)!r}")
    if spec.base_value_col:
        parts.append(f"base_value_col={spec.base_value_col!r}")
    if spec.note:
        parts.append(f"note={spec.note!r}")
    return "KeySpec(" + ", ".join(parts) + ")"


def render_formula_module(spec_mapping, *, template: str = "?", answer_key: str = "?") -> str:
    """KeySpecMapping → 완성된 .py 소스 문자열."""
    specs = sorted(spec_mapping.specs, key=lambda s: s.key)
    unresolved = sorted(spec_mapping.unresolved or [])

    formula_lines = "\n".join(f"    {_keyspec_literal(s)}," for s in specs) or "    # (없음)"
    unresolved_lines = "\n".join(f"    {u!r}," for u in unresolved) or "    # (없음)"

    return f'''"""계산식 코드 (AUTO-GENERATED) — 편집·단독 실행 가능.

Planner가 도출한 KPI 계산식(KeySpec)을 코드로 고정한 모듈이다.
최초 1회 생성 후, 이후 실행은 재도출 없이 이 파일을 import해 재사용한다.
계산식은 데이터 비의존이므로 raw_data가 바뀌면 같은 식으로 새 값을 낸다.

  source_template   : {template}
  source_answer_key : {answer_key}
  formula_count     : {len(specs)}
  unresolved_count  : {len(unresolved)}

이 파일을 직접 수정하면 다음 실행부터 수정된 식이 사용된다
(단, Planner 자아 진화 재시도 시에는 덮어써져 재생성된다).

단독 실행: python {{이_파일}} <data_dir> <cur_date> <prv_date>
"""
from __future__ import annotations

import os
import sys

# 단독 실행을 위해 프로젝트 루트를 import 경로에 추가
_ROOT = os.path.abspath(__file__)
for _ in range({_ROOT_UP}):
    _ROOT = os.path.dirname(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agents.models import KeySpec, KeySpecMapping
from core.predefined.formula_engine import execute_plan

# ── 계산식: 키별 KeySpec (sum(value_col)/sum(denom_col) × scale, period별 날짜) ──
FORMULAS: list[KeySpec] = [
{formula_lines}
]

# ── 명세를 세울 수 없던 키 (데이터/정의 부재) ──
UNRESOLVED: list[str] = [
{unresolved_lines}
]

PLAN = KeySpecMapping(specs=FORMULAS, unresolved=UNRESOLVED)


def compute_all(data_dir: str, cur_date: str, prv_date: str) -> dict:
    """고정된 계산식으로 모든 KPI 계산 → {{key: value|None}}."""
    return execute_plan(PLAN, data_dir, cur_date, prv_date)


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="고정 계산식 단독 실행")
    ap.add_argument("data_dir", help="parquet 폴더 ({{df_key}}.parquet)")
    ap.add_argument("cur_date", help="기준월 (예: 2026-04)")
    ap.add_argument("prv_date", help="전월 (예: 2026-03)")
    a = ap.parse_args()
    result = compute_all(a.data_dir, a.cur_date, a.prv_date)
    ok = sum(1 for v in result.values() if v is not None)
    print(f"# {{ok}}/{{len(result)}}개 계산 성공", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
'''


def emit_formula_module(spec_mapping, out_path: str, *, template: str = "?",
                        answer_key: str = "?") -> str:
    """KeySpecMapping을 .py 파일로 출력하고 경로 반환."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    src = render_formula_module(spec_mapping, template=template, answer_key=answer_key)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(src)
    return out_path


def load_formula_module(path: str) -> ModuleType:
    """생성된 계산식 .py를 in-process로 import해 모듈 반환 (compute_all 사용)."""
    spec = importlib.util.spec_from_file_location("_agen_formulas", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
