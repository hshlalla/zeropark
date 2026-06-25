"""① Reader 에이전트 — SlideMapping 생성 (JSON 캐시 지원).

첫 실행: LLM이 정답지를 분석 → SlideMapping 생성 → generated/mappings/mapping_{hash}.json 저장
재실행: JSON 캐시에서 즉시 로드 (LLM 호출 없음)
"""
from __future__ import annotations

import json
import os
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.state import AgentState
from agents.models import SlideMapping, ChartTarget
from core.predefined.pptx_scanner import scan_pptx_cached as scan_pptx, is_kpi_placeholder
from .kpi_discovery import scan_placeholders, check_mapping_completeness, check_duplicate_kpis
from agents.utils import load_skills, load_contract, template_hash, MAPPINGS_DIR, get_anthropic_api_key

_CONTRACT = load_contract("reader")   # agents/contracts/reader.md
_SKILLS   = load_skills("reader")     # agents/skills/reader.md

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        api_key = get_anthropic_api_key()
        _llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=api_key,
            max_tokens=64000,
            timeout=180,       # 한 요청이 180초 넘게 멈추면 끊음 (무한 hang 방지)
            max_retries=2,     # 끊기거나 일시 오류 시 자동 재시도
        )
    return _llm


def _infer_cell_format(cell_value: str) -> str | None:
    """템플릿 셀 placeholder 값으로 expected format_type 추론.

    None → 헤더/레이블 셀 (필터 적용 안 함)
    'text' → 인사이트 텍스트 셀 (항상 제외)
    """
    v = str(cell_value).strip()
    if not v:
        return None
    if v.startswith("{{"):          # 인사이트 텍스트 placeholder
        return "text"
    if re.search(r'\d+\.?\d*K\b', v):  # K단위 숫자 (예: 0.0K)
        return "kval"
    if "%p" in v:                   # MoM 변화량 (예: +0.0%p)
        return "mom"
    if re.match(r"x\d+\.?\d*", v):  # x-배수 비율 (예: x0.85)
        return "ratio"
    if "%" in v:                    # 퍼센트 (예: 0.0%)
        return "pct"
    return None


def _validate_mapping_vs_template(mapping: "SlideMapping",
                                  template_slides: list[dict]) -> "SlideMapping":
    """LLM이 생성한 SlideMapping을 템플릿 실제 구조와 대조해 유효한 targets만 남긴다.

    제거 대상:
    - 잘못된 slide_idx / shape_num
    - format_type='text' 인사이트 서술 셀
    - 템플릿 셀 placeholder 형식과 format_type이 불일치 (예: K값 셀에 pct)
    - row/col이 실제 테이블 범위 초과
    - 같은 (slide_idx, shape_num, row, col)에 두 번 할당된 경우 — 첫 번째만 유지
    텍스트 도형(shape_type='text')은 별도 추적해 허용.
    """
    template_tables: set[tuple[int, int]] = set()
    template_text_shapes: set[tuple[int, int]] = set()
    cell_format_map: dict[tuple, str] = {}  # (slide_idx, shape_num, row, col) → expected fmt
    table_dims: dict[tuple[int, int], tuple[int, int]] = {}  # (slide_idx, shape_num) → (rows, cols)

    for slide in template_slides:
        idx = slide["slide_idx"]
        for sh in slide["shapes"]:
            if sh["type"] == "table":
                shape_key = (idx, sh["num"])
                template_tables.add(shape_key)
                grid = sh.get("grid", [])
                if grid:
                    max_c = max((len(row) for row in grid), default=0)
                    table_dims[shape_key] = (len(grid), max_c)
                    for r, row in enumerate(grid):
                        for c, cell_val in enumerate(row):
                            fmt = _infer_cell_format(str(cell_val or ""))
                            if fmt is not None:
                                cell_format_map[(idx, sh["num"], r, c)] = fmt
            elif sh["type"] == "text" and sh.get("text"):
                if is_kpi_placeholder(sh["text"]):
                    template_text_shapes.add((idx, sh["num"]))

    before = len(mapping.targets)
    seen_cells: set[tuple] = set()
    valid = []

    for t in mapping.targets:
        shape_key = (t.slide_idx, t.shape_num)
        cell_key = (t.slide_idx, t.shape_num, t.row, t.col)
        s_type = getattr(t, "shape_type", "table")

        # 텍스트 도형 — 템플릿에 KPI 텍스트 도형으로 등록된 경우만 허용
        if s_type == "text":
            if shape_key not in template_text_shapes:
                continue
            if cell_key in seen_cells:
                continue
            seen_cells.add(cell_key)
            valid.append(t)
            continue

        # 표 셀 (기존 로직)
        if shape_key not in template_tables:
            continue
        if t.format_type == "text":
            continue

        # row/col 범위 초과 체크
        dims = table_dims.get(shape_key)
        if dims and (t.row >= dims[0] or t.col >= dims[1]):
            continue

        # 템플릿 셀 형식과 format_type 호환성 체크
        expected_fmt = cell_format_map.get(cell_key)
        if expected_fmt == "text":      # 인사이트 텍스트 셀 → 제외
            continue
        if expected_fmt is not None and expected_fmt != t.format_type:
            continue                     # 형식 불일치 → 제외

        # 중복 셀 제거 (첫 번째 할당 우선)
        if cell_key in seen_cells:
            continue
        seen_cells.add(cell_key)
        valid.append(t)

    removed = before - len(valid)
    if removed:
        print(f"[Reader] 템플릿 검증: {removed}개 유효하지 않은 target 제거 "
              f"(잘못된 slide/shape·텍스트 셀·형식 불일치·범위 초과·중복)")
    return SlideMapping(targets=valid)


def _enrich_shape_ids(mapping: "SlideMapping", *scans: list[dict]) -> None:
    """스캔 결과에서 (slide_idx, shape_num) → shape_id 역조회 후 targets에 채운다.

    여러 스캔을 우선순위 순으로 받아 첫 번째로 찾은 값을 사용한다.
    이미 채워진 shape_id는 덮어쓰지 않는다.
    """
    lookup: dict[tuple[int, int], int] = {}
    for scan in scans:
        for slide in scan:
            idx = slide["slide_idx"]
            for sh in slide["shapes"]:
                num = sh.get("num")
                sid = sh.get("shape_id")
                if num is not None and sid is not None:
                    lookup.setdefault((idx, num), sid)

    for t in mapping.targets:
        if t.shape_id is None:
            t.shape_id = lookup.get((t.slide_idx, t.shape_num))


# 이 행 수를 초과하는 테이블은 LLM에 헤더+청크 단위로 분할 전송한다.
# 슬라이드별 개별 처리이므로 토큰 초과 걱정 없이 전체 테이블을 매핑할 수 있다.
_MAX_TABLE_ROWS_FOR_LLM = 30


def _format_blocks(idx: int, blocks: list[dict], shapes: list[dict]) -> list[str]:
    """Smart Block 목록을 LLM용 compact 텍스트로 변환.

    KPI_CARD: label + 표 데이터를 한 블록으로 묶어 출력
    TABLE_SECTION: 대형 표 전체 출력
    CHART: 차트 존재 표시
    LABEL: 섹션 헤더·미분류 텍스트
    """
    # shape_num → shape dict 역조회
    shape_map = {s.get("num"): s for s in shapes}
    lines: list[str] = []

    for blk in blocks:
        bt = blk["block_type"]

        if bt == "KPI_CARD":
            label = blk.get("label") or ""
            tnum  = blk.get("table_num")
            label_tag = f" label={label!r}" if label else ""
            lines.append(f"\n[slide={idx} block=KPI_CARD{label_tag} table_num={tnum}]")
            tbl = shape_map.get(tnum)
            if tbl and tbl.get("grid"):
                for r, row in enumerate(tbl["grid"]):
                    row_vals = [str(v or "") for v in row]
                    lines.append(f"  row{r}: {row_vals}")

        elif bt == "TABLE_SECTION":
            tnum = blk.get("table_num")
            rows = blk.get("rows", 0)
            cols = blk.get("cols", 0)
            lines.append(f"\n[slide={idx} block=TABLE_SECTION table_num={tnum} rows={rows} cols={cols}]")
            tbl = shape_map.get(tnum)
            if tbl and tbl.get("grid"):
                for r, row in enumerate(tbl["grid"]):
                    row_vals = [str(v or "") for v in row]
                    lines.append(f"  row{r}: {row_vals}")

        elif bt == "CHART":
            lines.append(f"[slide={idx} block=CHART shape_num={blk.get('shape_num')}]")

        elif bt == "LABEL":
            text = blk.get("text", "")
            if text:
                lines.append(f"[slide={idx} block=LABEL text={text!r}]")

    # KPI 수치 텍스트 도형은 blocks에 포함 안 되므로 별도 출력
    for sh in shapes:
        if sh.get("type") == "text" and sh.get("text"):
            text = sh["text"].strip()
            if is_kpi_placeholder(text):
                num  = sh.get("num")
                name = sh.get("name", "")
                lines.append(f"\n[slide={idx} shape_num={num} name={name!r} type=text]")
                lines.append(f"  text: {text!r}")

    return lines


def _format_answer_key(ans_slides: list[dict]) -> str:
    """정답지 슬라이드를 LLM이 읽기 쉬운 compact 텍스트로 변환.

    blocks 필드가 있으면 Smart Block 형식으로 출력 (label+table 쌍이 명시됨).
    없으면 shape 단위 flat 출력으로 fallback.
    """
    lines = []
    for slide in ans_slides:
        idx = slide["slide_idx"]
        if idx < 2:
            continue

        if "blocks" in slide:
            # Smart Block 형식 — label과 table이 하나의 block으로 묶여 출력됨
            lines.extend(_format_blocks(idx, slide["blocks"], slide["shapes"]))
        else:
            # Fallback: shape 단위 flat 출력 (구 캐시 호환)
            shapes = sorted(slide["shapes"], key=lambda s: s.get("z_order", 0))
            for sh in shapes:
                if sh["type"] == "table" and sh.get("grid"):
                    num  = sh.get("num")
                    name = sh.get("name", "")
                    grid = sh["grid"]
                    lines.append(f"\n[slide={idx} shape_num={num} name={name!r} type=table rows={len(grid)}]")
                    for r, row in enumerate(grid):
                        lines.append(f"  row{r}: {[str(v or '') for v in row]}")
                elif sh["type"] == "text" and sh.get("text"):
                    text = sh["text"].strip()
                    if not text:
                        continue
                    num  = sh.get("num")
                    name = sh.get("name", "")
                    if is_kpi_placeholder(text):
                        lines.append(f"\n[slide={idx} shape_num={num} name={name!r} type=text]")
                        lines.append(f"  text: {text!r}")
                    else:
                        lines.append(f"[slide={idx} shape_num={num} label={text!r}]")
    return "\n".join(lines)


def _slides_with_tables(ans_slides: list[dict]) -> list[dict]:
    """테이블 또는 KPI 텍스트 도형이 있는 슬라이드 반환 (slide_idx >= 2)."""
    result = []
    for s in ans_slides:
        if s["slide_idx"] < 2:
            continue
        has_table = any(sh["type"] == "table" and sh.get("grid") for sh in s["shapes"])
        has_kpi_text = any(
            sh["type"] == "text" and sh.get("text") and is_kpi_placeholder(sh["text"])
            for sh in s["shapes"]
        )
        if has_table or has_kpi_text:
            result.append(s)
    return result


def _call_llm_for_slides(llm, slides_batch: list[dict]) -> "SlideMapping":
    """슬라이드 일부에 대한 LLM 호출 → 부분 SlideMapping 반환."""
    ans_text = _format_answer_key(slides_batch)
    idxs = sorted({s["slide_idx"] for s in slides_batch})

    system_content = _CONTRACT
    if _SKILLS:
        system_content += f"\n\n---\n## Reader Skills (반드시 준수)\n{_SKILLS}"

    user_msg = f"""## 정답지 셀값 (슬라이드 {idxs})
{ans_text}

위 슬라이드들을 분석해서 각 셀/도형에 어떤 KPI 값이 들어가는지 매핑을 생성해주세요.

반환 형식은 다음 JSON 구조입니다:
{{
  "targets": [
    {{
      "slide_idx": 3,
      "shape_num": 147,
      "shape_name": "표 147",
      "shape_type": "table",
      "row": 0,
      "col": 0,
      "value_key": "rv_support_samsung_global_cur",
      "format_type": "pct",
      "block_type": "KPI_CARD",
      "block_label": "Support",
      "context": "Samsung RV Support 채널 현월 글로벌 %"
    }},
    ...
  ]
}}

입력 형식 안내:
- `[block=KPI_CARD label='Support' table_num=147]` — Smart Block: label이 이 표의 세그먼트 이름
  → value_key에 세그먼트를 반영하세요 (예: rv_support_*), block_label에 label 값 기입
- `[block=TABLE_SECTION table_num=80]` — 대형 KPI 테이블
- `[block=LABEL text='By Channel (%)']` — 섹션 헤더 (매핑 제외)
- `[type=text]` — KPI 수치가 있는 텍스트 도형

주의:
- 실제 KPI 수치(%, %p, K, x배수 등)가 있는 셀/도형만 포함
- "MoM", "Country" 등 고정 레이블 제외. 빈 셀 제외
- block=KPI_CARD 안의 같은 슬라이드 내 여러 표는 label이 다르면 반드시 다른 value_key 사용
- 동일 KPI가 여러 슬라이드에 있으면 동일한 value_key 사용 (중복 key 생성 금지)"""
    return llm.invoke([
        SystemMessage(content=system_content),
        HumanMessage(content=user_msg),
    ])


def _register_shapes(mapping: "SlideMapping") -> None:
    """매핑된 도형을 공유 메모리 shape_registry에 기록 (role=value_key)."""
    try:
        from core.predefined.shared_memory import get_memory
        rows = [(t.slide_idx, t.shape_id, getattr(t, "shape_type", "table"),
                 t.value_key, t.value_key) for t in mapping.targets]
        get_memory().register_shapes_bulk(rows)
    except Exception:
        pass


def _extract_chart_targets(ans_slides: list[dict]) -> list[ChartTarget]:
    """정답지 스캔에서 차트 계열(ChartTarget) 스텁 생성 (fit 없음, 구조만)."""
    from core.predefined.chart_fill import parse_months
    chart_targets: list[ChartTarget] = []
    for sl in ans_slides:
        sidx = sl["slide_idx"]
        if sidx < 2:
            continue
        for sh in sl["shapes"]:
            if sh.get("type") != "chart":
                continue
            chart_info = sh.get("chart") or {}
            if not chart_info.get("series"):
                continue
            snum = sh.get("num")
            shape_id = sh.get("shape_id")
            cats = chart_info.get("categories") or []
            months = parse_months(cats)
            is_time = sum(1 for m in months if m) >= max(2, len(cats) // 2)
            for si, s in enumerate(chart_info.get("series", [])):
                sname = s.get("name") or f"series{si}"
                ct = ChartTarget(
                    slide_idx=sidx, shape_num=snum, shape_id=shape_id,
                    categories=cats, series_name=str(sname), series_idx=si,
                    category_kind="time" if is_time else "category",
                    value_key=f"chart_s{sidx}_{snum}_{si}",
                )
                chart_targets.append(ct)
    return chart_targets


def read_template(state: AgentState) -> dict:
    """정답지 + 템플릿을 분석해 SlideMapping 생성. 캐시 히트 시 LLM 없이 JSON 로드.

    반환: slide_mapping (override), template_schema (override), messages (append)
    """
    template_path = state["template_path"]
    answer_key_path = state.get("answer_key_path")

    # ── 캐시 확인 (최우선·결정론적, LLM 없음) ──────────────────────────
    # 캐시 키 = 템플릿 파일 해시. SlideMapping은 (좌표→value_key) 구조 매핑이라
    # 템플릿 디자인/플레이스홀더 위치에만 의존한다. 매달 바뀌는 정답지 값·raw data·
    # target_month 와 무관하므로, 템플릿이 그대로면 캐시를 그대로 재사용한다.
    # → 매달 보고서 작업에서 가장 무거운 Reader LLM 호출을 통째로 건너뛴다.
    os.makedirs(MAPPINGS_DIR, exist_ok=True)
    t_hash = template_hash(template_path)
    cache_path = os.path.join(MAPPINGS_DIR, f"mapping_{t_hash}.json")

    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            mapping = SlideMapping(**data)
            if not mapping.targets:
                print("[Reader] 빈 캐시 감지 → 삭제 후 LLM 재생성")
                os.remove(cache_path)
            else:
                # 구 캐시에 shape_id가 없거나 chart_targets가 없으면 1회 스캔해 보충
                missing_ids = sum(1 for t in mapping.targets if t.shape_id is None)
                need_charts = (not mapping.chart_targets
                               and answer_key_path and os.path.exists(answer_key_path))
                if missing_ids or need_charts:
                    try:
                        ak_scan = scan_pptx(answer_key_path, read_values=True) if answer_key_path and os.path.exists(answer_key_path) else []
                        tmpl_scan = scan_pptx(template_path, read_values=False)
                        if missing_ids:
                            _enrich_shape_ids(mapping, ak_scan, tmpl_scan)
                            print(f"[Reader] shape_id {missing_ids}개 보충")
                        if need_charts and ak_scan:
                            chart_targets = _extract_chart_targets(ak_scan)
                            mapping = SlideMapping(targets=mapping.targets,
                                                   chart_targets=chart_targets)
                            print(f"[Reader] chart_targets 보충: {len(chart_targets)}개 계열")
                        with open(cache_path, "w", encoding="utf-8") as wf:
                            json.dump(mapping.model_dump(), wf, ensure_ascii=False, indent=2)
                        print("[Reader] 캐시 갱신 완료")
                    except Exception as e:
                        print(f"[Reader] 캐시 보충 실패(무시): {e}")
                # Skill 2(coverage 검증)는 캐시 히트 시 생략한다.
                #   캐시 키가 템플릿 해시 == 템플릿이 바이트 단위로 동일 → 생성 시점과
                #   coverage 결과가 동일하므로 재검증은 중복이며 템플릿 재스캔만 낭비된다.
                msg = (f"SlideMapping 캐시 즉시 로드 (LLM 건너뜀): "
                       f"{len(mapping.targets)}개 셀, {len(mapping.unique_keys)}개 키")
                print(f"[Reader] ⚡ {msg} (template_hash={t_hash})")
                _kpi_counts = {**(state.get("kpi_counts") or {}), "reader": len(mapping.targets)}
                print(f"[Pipeline] KPI Conservation [reader]: {len(mapping.targets)}")
                _register_shapes(mapping)
                return {
                    "slide_mapping": mapping,
                    "template_schema": None,
                    "kpi_counts": _kpi_counts,
                    "pending_gate": "after_mapping",
                    "messages": [AIMessage(content=msg, name="Reader")],
                }
        except Exception as e:
            print(f"[Reader] 캐시 로드 실패 ({e}) — LLM 재생성")

    # ── 템플릿 스캔 (read_values=True: 셀 형식 검증용 grid 포함) ────
    print(f"[Reader] 템플릿 스캔: {template_path}")
    try:
        template_slides = scan_pptx(template_path, read_values=True)
    except Exception as e:
        return {"errors": [f"템플릿 스캔 실패: {e}"]}

    if not answer_key_path or not os.path.exists(answer_key_path):
        print("[Reader] 정답지 없음 — 빈 SlideMapping 생성")
        return {
            "slide_mapping": SlideMapping(),
            "template_schema": {"template_slides": template_slides, "answer_key_slides": None},
            "messages": [AIMessage(content="정답지 없음 — SlideMapping 비어있음", name="Reader")],
        }

    print(f"[Reader] 정답지 스캔: {answer_key_path}")
    try:
        ans_slides = scan_pptx(answer_key_path, read_values=True)
    except Exception as e:
        return {"errors": [f"정답지 스캔 실패: {e}"]}

    # ── 슬라이드별 개별 처리 ─────────────────────────────────────────
    # 대형 테이블(16행×14열 등)을 포함하는 슬라이드는 출력 토큰이 많아서
    # 여러 슬라이드를 묶으면 max_tokens를 초과해 빈 결과가 나올 수 있다.
    # 슬라이드 단위로 개별 호출해 안전하게 처리한다.

    table_slides = _slides_with_tables(ans_slides)
    if not table_slides:
        err = "정답지에 표가 없습니다 — 정답지 PPT를 확인하세요."
        print(f"[Reader] ERROR: {err}")
        return {"errors": [err]}

    total_tables = sum(
        sum(1 for sh in s["shapes"] if sh["type"] == "table" and sh.get("grid"))
        for s in table_slides
    )
    n_slides = len(table_slides)
    print(f"[Reader] LLM SlideMapping 생성 중 — "
          f"{n_slides}개 슬라이드 / {total_tables}개 테이블 (슬라이드별 개별 처리)")

    llm = _get_llm().with_structured_output(SlideMapping)
    all_targets = []

    for i, slide in enumerate(table_slides, 1):
        idx = slide["slide_idx"]
        n_t = sum(1 for sh in slide["shapes"]
                  if sh["type"] == "table" and sh.get("grid"))
        n_kpi_text = sum(1 for sh in slide["shapes"]
                         if sh["type"] == "text" and sh.get("text")
                         and is_kpi_placeholder(sh["text"]))
        # 순번(i)과 실제 슬라이드 번호(slide_idx)를 명확히 구분해 표기
        print(f"[Reader] 처리 {i}/{n_slides} → slide_idx={idx} "
              f"(테이블 {n_t}개, KPI텍스트 {n_kpi_text}개)")
        try:
            partial: SlideMapping = _call_llm_for_slides(llm, [slide])
            # LLM이 가끔 slide_idx를 잘못 설정하므로 현재 슬라이드로 강제 교정
            wrong = sum(1 for t in partial.targets if t.slide_idx != idx)
            if wrong:
                for t in partial.targets:
                    t.slide_idx = idx
                print(f"[Reader]   slide_idx 교정: {wrong}개 → {idx}")
            all_targets.extend(partial.targets)
            print(f"[Reader]   → {len(partial.targets)}개 targets")
        except Exception as e:
            print(f"[Reader]   slide={idx} 실패 ({e}) — 건너뜀")

    if not all_targets:
        err = ("SlideMapping이 비어있습니다 — LLM이 매핑을 생성하지 못했습니다. "
               "정답지 표 구조를 확인하거나 --regenerate로 재시도하세요.")
        print(f"[Reader] ERROR: {err}")
        return {"errors": [err]}

    mapping = SlideMapping(targets=all_targets)

    # ── 템플릿 검증: 잘못된 slide/shape 및 text 인사이트 셀 제거 ──────
    mapping = _validate_mapping_vs_template(mapping, template_slides)
    if not mapping.targets:
        err = "템플릿 검증 후 유효한 targets가 없습니다 — 정답지/템플릿 구조를 확인하세요."
        print(f"[Reader] ERROR: {err}")
        return {"errors": [err]}

    # ── 차트 타깃 추출 (정답지 차트 구조 → ChartTarget 스텁, fit 없음) ──
    chart_targets = _extract_chart_targets(ans_slides)
    mapping = SlideMapping(targets=mapping.targets, chart_targets=chart_targets)
    if chart_targets:
        print(f"[Reader] 차트 타깃 추출: {len(chart_targets)}개 계열")

    # ── shape_id 보강 (스캔 결과에서 역조회) ─────────────────────────
    _enrich_shape_ids(mapping, ans_slides, template_slides)

    # ── 캐시 저장 (shape_id 포함, 비어있지 않을 때만) ──────────────
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(mapping.model_dump(), f, ensure_ascii=False, indent=2)

    n = len(mapping.targets)
    unique_keys = len(mapping.unique_keys)
    msg = f"SlideMapping 생성: {n}개 셀, {unique_keys}개 KPI 키 → 캐시 저장"
    print(f"[Reader] {msg}")

    # Skill 2: 생성 후 completeness 검증 (template_slides는 이미 메모리에 있음)
    if _SKILLS:
        placeholders = scan_placeholders(template_slides)
        result = check_mapping_completeness(placeholders, mapping)
        table_cov = f"{result.table_mapped}/{result.table_total} ({result.table_mapped/result.table_total:.0%})" if result.table_total else "N/A"
        text_cov  = f"{result.text_mapped}/{result.text_total} ({result.text_mapped/result.text_total:.0%})" if result.text_total else "N/A"
        print(f"[Reader] [Skill 2] Table: {table_cov} | Text: {text_cov} | Chart: {result.chart_total}개")
        if not result.passed:
            fail_msg = (f"[Skill 2] FAIL: coverage={result.coverage:.1%} < 95% "
                        f"(미매핑 {len(result.unmapped)}개)")
            print(f"[Reader] ⚠ {fail_msg}")
            skill2_warnings = [fail_msg]
        else:
            print(f"[Reader] [Skill 2] ✓ coverage {result.coverage:.1%} — PASS")
            skill2_warnings = []
        dup = check_duplicate_kpis(mapping)
        print(f"[Reader] [Skill 2] Duplicate KPI: {dup['multi_location_keys']}개 키 다중 위치")
    else:
        skill2_warnings = []

    _kpi_counts = {**(state.get("kpi_counts") or {}), "reader": len(mapping.targets)}
    print(f"[Pipeline] KPI Conservation [reader]: {len(mapping.targets)}")
    _register_shapes(mapping)
    return {
        "slide_mapping": mapping,
        "template_schema": {
            "template_slides": template_slides,
            "answer_key_slides": ans_slides,
        },
        "kpi_counts": _kpi_counts,
        "pending_gate": "after_mapping",
        "messages": [AIMessage(content=msg, name="Reader")],
        "errors": skill2_warnings,
    }
