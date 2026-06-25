"""PPT_AGENT — 멀티 에이전트 PPT 자동 채우기 엔진.

external/ppt_automation (LangGraph 기반)을 래핑한다.
파이프라인: analyze_data → read_template → plan_formulas → calculate_kpis
           → fill_pptx → verify_output → write_insights

필수 params:
  template_path  (str)  : .pptx 템플릿 경로
  raw_data_dir   (str)  : raw_data/ 폴더 경로 (기본: external/ppt_automation/raw_data)

선택 params:
  answer_key_path (str)  : 정답지 .pptx 경로
  output_path     (str)  : 출력 경로 (기본: external/ppt_automation/output/filled_<task_id>.pptx)
  target_month    (str)  : 기준월 (예: "2026-04")
  regenerate      (bool) : True → 캐시 무시 후 LLM 재생성

환경변수:
  PPT_AGENT_DIR : external/ppt_automation 절대경로 (생략 시 워크스페이스 상대경로 자동 계산)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from zeropark_core.capabilities import Capability
from zeropark_core.models import Artifact, RunEvent, TaskRequest, TaskResult, TaskStatus
from zeropark_core.store import ArtifactStore

from zeropark_engines.base import NativeEngine

_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _ppt_agent_dir() -> Path:
    env = os.environ.get("PPT_AGENT_DIR")
    if env:
        return Path(env).resolve()
    # packages/zeropark-engines/src/zeropark_engines/ → (4 up) → packages/ → (1 up) → root
    return (Path(__file__).parent.parent.parent.parent.parent / "external" / "ppt_automation").resolve()


def _ensure_sys_path() -> None:
    d = str(_ppt_agent_dir())
    if d not in sys.path:
        sys.path.insert(0, d)


def _build_initial_state(params: dict[str, Any], output_path: str, ppt_dir: Path) -> dict[str, Any]:
    return {
        "template_path":        params.get("template_path"),
        "answer_key_path":      params.get("answer_key_path"),
        "raw_data_dir":         params.get("raw_data_dir", str(ppt_dir / "raw_data")),
        "output_path":          output_path,
        "target_month":         params.get("target_month"),
        "data_schema":          None,
        "data_cache_dir":       None,
        "template_schema":      None,
        "slide_mapping":        None,
        "key_spec_mapping":     None,
        "calculation_result":   None,
        "execution_output_path": None,
        "kpi_code_path":        None,
        "verification_result":  None,
        "validation_issues":    None,
        "fill_report":          None,
        "pending_gate":         None,
        "retry_count":          0,
        "retry_feedback":       None,
        "generated_code_path":  None,
        "chart_counts":         None,
        "messages":             [],
        "errors":               [],
        "gate_results":         [],
    }


class PptAutoEngine(NativeEngine):
    """LangGraph 멀티 에이전트 파이프라인으로 PPT 보고서를 자동 채우는 엔진.

    external/ppt_automation의 코드를 복사하지 않고 sys.path로 직접 임포트한다.
    external은 ./run.sh로 독립 실행도 유지된다.
    """

    id = "zeropark_engines.ppt_agent"
    name = "PPT Auto Agent Engine"
    capabilities = {Capability.PPT_AGENT}
    reference = "internal — external/ppt_automation (LangGraph multi-agent pipeline)"

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store
        _ensure_sys_path()

    def _run_pipeline(self, params: dict[str, Any], output_path: str) -> dict[str, Any]:
        from agents.graph import get_app  # noqa: PLC0415 — imported after sys.path injection

        ppt_dir = _ppt_agent_dir()

        if params.get("regenerate"):
            self._clear_cache(ppt_dir, params.get("template_path", ""))

        state = _build_initial_state(params, output_path, ppt_dir)
        return get_app().invoke(state, {"recursion_limit": 120})

    @staticmethod
    def _clear_cache(ppt_dir: Path, template_path: str) -> None:
        import glob as _glob
        from agents.utils import MAPPINGS_DIR, PLANS_DIR, template_hash  # noqa: PLC0415

        if template_path:
            mapping = Path(MAPPINGS_DIR) / f"mapping_{template_hash(template_path)}.json"
            mapping.unlink(missing_ok=True)
        for f in _glob.glob(str(Path(PLANS_DIR) / "formula_plan_*.json")):
            Path(f).unlink(missing_ok=True)

    async def cap_ppt_agent(self, task: TaskRequest, task_id: str) -> TaskResult:
        params = task.params or {}
        ppt_dir = _ppt_agent_dir()
        output_path = params.get("output_path") or str(
            ppt_dir / "output" / f"filled_{task_id}.pptx"
        )

        loop = asyncio.get_event_loop()
        final = await loop.run_in_executor(
            None, lambda: self._run_pipeline(params, output_path)
        )

        out = final.get("execution_output_path") or output_path
        errors: list[str] = final.get("errors") or []

        if not Path(out).exists():
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                capability=Capability.PPT_AGENT,
                provider_id=self.id,
                artifacts=[],
                metrics={"errors": len(errors)},
            )

        pptx_bytes = Path(out).read_bytes()
        file_uri = self.store.save(f"{task_id}.pptx", pptx_bytes)

        artifacts = [Artifact(
            id=f"{task_id}_ppt",
            kind="deck",
            title=params.get("title", f"Report {task_id}"),
            mime_type=_PPTX_MIME,
            uri=file_uri,
        )]

        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.PPT_AGENT,
            provider_id=self.id,
            artifacts=artifacts,
            metrics={"errors": len(errors)},
        )

    async def stream(self, task: TaskRequest, *, task_id: str):  # type: ignore[override]
        yield RunEvent(
            type="status", task_id=task_id, provider_id=self.id,
            message="started", data={"capability": task.capability.value},
        )
        yield RunEvent(
            type="log", task_id=task_id, provider_id=self.id,
            message="[PPT Agent] LangGraph 파이프라인 시작 (analyze → read → plan → calc → fill → verify → insight)...",
        )
        try:
            result = await self.cap_ppt_agent(task, task_id)
            for artifact in result.artifacts:
                yield RunEvent(
                    type="artifact", task_id=task_id, provider_id=self.id,
                    data={"artifact": artifact.model_dump(mode="json")},
                )
            yield RunEvent(
                type="done", task_id=task_id, provider_id=self.id,
                data={"status": result.status.value, "result": result.model_dump(mode="json")},
            )
        except Exception as exc:
            yield RunEvent(type="error", task_id=task_id, provider_id=self.id, message=str(exc))
