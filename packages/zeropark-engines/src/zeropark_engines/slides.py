"""SLIDES — render an outline to a real .pptx. Native (python-pptx).

Design reference: Presenton (Apache-2.0). No Presenton code or service is used.
Content generation (turning a prompt into an outline) is a pluggable LLM step;
this engine renders whatever outline it is given, so it works with zero config.
"""

from __future__ import annotations

import json
import re
import asyncio
import io
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt
from zeropark_core.capabilities import Capability
from zeropark_core import ArtifactStore
from zeropark_core.models import Artifact, TaskRequest, TaskResult, TaskStatus
from zeropark_core.llm import BaseLLMClient, ChatMessage

from zeropark_engines.base import NativeEngine

_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _hex_to_rgb(value: str) -> RGBColor:
    value = value.lstrip("#")
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


# Built-in themes (Presenton-style template layer). A deployment can also pass
# a fully custom theme dict in task params — e.g. matched to client branding.
THEMES: dict[str, dict[str, Any]] = {
    "default": {
        "background": "#FFFFFF",
        "title_color": "#1F2937",
        "body_color": "#374151",
        "accent": "#4F46E5",
        "font": "Calibri",
    },
    "dark": {
        "background": "#111827",
        "title_color": "#F9FAFB",
        "body_color": "#D1D5DB",
        "accent": "#818CF8",
        "font": "Calibri",
    },
    "corporate": {
        "background": "#F8FAFC",
        "title_color": "#0F172A",
        "body_color": "#334155",
        "accent": "#0EA5E9",
        "font": "Arial",
    },
}


def resolve_theme(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve a theme: named theme + optional per-key overrides (e.g. accent
    set to the deployment's branding primary color)."""
    theme = dict(THEMES.get(str(params.get("theme", "default")), THEMES["default"]))
    overrides = params.get("theme_overrides") or {}
    theme.update({k: v for k, v in overrides.items() if k in theme})
    return theme


class PptxSlidesEngine(NativeEngine):
    id = "zeropark_engines.slides.pptx"
    name = "Pptx Renderer Engine"
    capabilities = {Capability.SLIDES}
    reference = "Presenton (Apache-2.0) - design reference only"

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    @staticmethod
    def _paint_background(slide, theme: dict) -> None:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = _hex_to_rgb(theme["background"])

    @staticmethod
    def _style_text_frame(text_frame, *, color: str, font: str, size: int, bold: bool = False) -> None:
        for paragraph in text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = _hex_to_rgb(color)
                run.font.name = font
                run.font.size = Pt(size)
                run.font.bold = bold

    def _render_pptx(
        self, title: str, subtitle: str, outline: list[dict], theme: dict | None = None
    ) -> bytes:
        theme = theme or THEMES["default"]
        prs = Presentation()

        title_slide = prs.slides.add_slide(prs.slide_layouts[0])
        self._paint_background(title_slide, theme)
        title_slide.shapes.title.text = title
        self._style_text_frame(
            title_slide.shapes.title.text_frame,
            color=theme["accent"], font=theme["font"], size=40, bold=True,
        )
        if len(title_slide.placeholders) > 1:
            title_slide.placeholders[1].text = subtitle
            self._style_text_frame(
                title_slide.placeholders[1].text_frame,
                color=theme["body_color"], font=theme["font"], size=18,
            )

        for item in outline:
            # speaker-note / section support: {"layout": "section"} renders a divider
            layout_index = 2 if item.get("layout") == "section" else 1
            slide = prs.slides.add_slide(prs.slide_layouts[layout_index])
            self._paint_background(slide, theme)
            slide.shapes.title.text = item.get("title", "")
            self._style_text_frame(
                slide.shapes.title.text_frame,
                color=theme["title_color"], font=theme["font"], size=30, bold=True,
            )
            bullets = item.get("bullets", []) or []
            if bullets and len(slide.placeholders) > 1:
                body = slide.placeholders[1].text_frame
                body.text = str(bullets[0])
                for bullet in bullets[1:]:
                    body.add_paragraph().text = str(bullet)
                self._style_text_frame(
                    body, color=theme["body_color"], font=theme["font"], size=18,
                )
            notes = item.get("notes")
            if notes:
                slide.notes_slide.notes_text_frame.text = str(notes)

        bio = io.BytesIO()
        prs.save(bio)
        return bio.getvalue()

    async def cap_slides(self, task: TaskRequest, task_id: str) -> TaskResult:
        outline = task.params.get("outline") or [
            {"title": task.params.get("title") or task.prompt[:80], "bullets": []}
        ]
        deck_title = task.params.get("title") or outline[0].get("title") or task.prompt[:80]
        subtitle = task.params.get("subtitle", "Generated by Zeropark")

        theme = resolve_theme(task.params)
        pptx_bytes = self._render_pptx(deck_title, subtitle, outline, theme=theme)
        
        # Save to store
        filename = f"{task_id}.pptx"
        file_uri = self.store.save(filename, pptx_bytes)

        n_slides = len(outline) + 1
        artifact = Artifact(
            id=f"{task_id}_deck",
            kind="deck",
            title=deck_title,
            mime_type=_PPTX_MIME,
            uri=file_uri,
            metadata={"slides": n_slides},
        )
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.SLIDES,
            provider_id=self.id,
            artifacts=[artifact],
            metrics={"slides": n_slides},
        )

class LLMSlidesEngine(NativeEngine):
    id = "llm-slides"
    name = "LLM Slides Generator"
    capabilities = frozenset({Capability.SLIDES})
    reference = "Presenton (Apache-2.0) - LLM Outline Generation"

    def __init__(self, llm_client: BaseLLMClient, renderer: PptxSlidesEngine, model_name: str = "gpt-4o-mini") -> None:
        self.llm_client = llm_client
        self.renderer = renderer
        self.model_name = model_name

    async def _generate_outline(self, prompt: str) -> list[dict]:
        system_msg = ChatMessage(
            role="system",
            content=(
                "You are an expert presentation designer. Create an outline for a slide deck based on the user's prompt. "
                "The outline must be in a strict JSON array format where each element represents a slide. "
                "Structure: [{\"title\": \"Slide Title\", \"bullets\": [\"Point 1\", \"Point 2\"], \"notes\": \"speaker notes\"}]. "
                "Generate 4 to 8 slides with concise, punchy bullets (max 8 words each) and helpful speaker notes. "
                "Return ONLY the JSON array, nothing else."
            )
        )
        user_msg = ChatMessage(role="user", content=prompt)
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.llm_client.chat_completion([system_msg, user_msg], self.model_name, temperature=0.5)
        )
        
        text = response.content.strip()
        # Find JSON array using regex if there's markdown wrapping
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            text = match.group(0)
            
        try:
            outline = json.loads(text)
            if isinstance(outline, list) and len(outline) > 0:
                return outline
        except Exception:
            pass
            
        # Fallback if parsing fails
        return [{"title": prompt[:80], "bullets": ["Could not generate detailed outline."]}]

    async def cap_slides(self, task: TaskRequest, task_id: str) -> TaskResult:
        # 1. Generate Outline via LLM
        outline = await self._generate_outline(task.prompt)
        
        # 2. Inject outline into task params
        if not task.params:
            task.params = {}
        task.params["outline"] = outline
        
        # 3. Delegate to renderer
        return await self.renderer.cap_slides(task, task_id)
