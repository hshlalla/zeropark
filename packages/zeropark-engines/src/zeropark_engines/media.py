"""MEDIA engines: IMAGE (generation), PAGE (single-file web page), AUDIO (podcast).

All three are thin native engines over the configured LLM provider:
  * ImageEngine    — OpenAI Images API → png artifact
  * PageEngine     — LLM writes one self-contained HTML document → page artifact
  * PodcastEngine  — LLM writes a two-host script, TTS per line, concatenated mp3

Image/TTS need the OpenAI SDK client, so those two register only when the
deployment's LLM provider is OpenAI-compatible; PAGE works with any provider.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time

from zeropark_core import ArtifactStore
from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.models import Artifact, TaskRequest, TaskResult, TaskStatus
from zeropark_engines.base import NativeEngine


def _openai_sdk(llm_client: BaseLLMClient):
    """The raw OpenAI SDK client when the provider exposes one, else None."""
    return getattr(llm_client, "client", None)


class ImageEngine(NativeEngine):
    id = "openai-image"
    name = "Image Generation Engine"
    capabilities = frozenset({Capability.IMAGE})
    reference = "OpenAI Images API"

    def __init__(self, store: ArtifactStore, llm_client: BaseLLMClient, *, model: str = "gpt-image-1") -> None:
        self.store = store
        self.llm_client = llm_client
        self.model = model

    async def cap_image(self, task: TaskRequest, task_id: str) -> TaskResult:
        sdk = _openai_sdk(self.llm_client)
        if sdk is None:
            return TaskResult(
                task_id=task_id, status=TaskStatus.FAILED, capability=Capability.IMAGE,
                provider_id=self.id, error="Image generation requires an OpenAI-compatible provider.",
            )
        start = time.time()
        size = task.params.get("size", "1024x1024")
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: sdk.images.generate(
                    model=task.params.get("model") or self.model,
                    prompt=task.prompt, size=size, n=1,
                ),
            )
            image_b64 = response.data[0].b64_json
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            return TaskResult(
                task_id=task_id, status=TaskStatus.FAILED, capability=Capability.IMAGE,
                provider_id=self.id, error=f"Image generation failed: {exc}",
            )
        uri = self.store.save(f"{task_id}.png", image_bytes)
        artifact = Artifact(
            id=self.new_id("image"), kind="image", title=task.prompt[:60],
            mime_type="image/png", uri=uri,
        )
        return TaskResult(
            task_id=task_id, status=TaskStatus.SUCCEEDED, capability=Capability.IMAGE,
            provider_id=self.id, artifacts=[artifact],
            metrics={"latency_ms": round((time.time() - start) * 1000, 2), "size": size},
        )


PAGE_PROMPT = """You are an expert web designer. Produce ONE complete, self-contained
HTML document (inline CSS, no external assets, no JS frameworks; vanilla JS allowed)
implementing the user's request. Modern, responsive, polished. Return ONLY the HTML
document starting with <!DOCTYPE html> — no markdown fences, no commentary."""


class PageEngine(NativeEngine):
    id = "llm-page"
    name = "Web Page Generator"
    capabilities = frozenset({Capability.PAGE})
    reference = "Native single-file page generator"

    def __init__(self, store: ArtifactStore, llm_client: BaseLLMClient, *, model: str = "gpt-4o-mini") -> None:
        self.store = store
        self.llm_client = llm_client
        self.model = model

    async def cap_page(self, task: TaskRequest, task_id: str) -> TaskResult:
        start = time.time()
        response = await self.llm_client.achat_completion(
            [
                ChatMessage(role="system", content=PAGE_PROMPT),
                ChatMessage(role="user", content=task.prompt),
            ],
            model=task.params.get("model") or self.model,
        )
        html = response.content.strip()
        match = re.search(r"<!DOCTYPE html.*</html>", html, re.DOTALL | re.IGNORECASE)
        if match:
            html = match.group(0)
        filename = f"{task_id}.html"
        uri = self.store.save(filename, html)
        artifact = Artifact(
            id=self.new_id("page"), kind="page", title=task.prompt[:60],
            mime_type="text/html", uri=uri,
            # the gateway serves the artifacts dir statically — relative link for the UI
            metadata={"public_path": f"/artifacts/{filename}"},
        )
        return TaskResult(
            task_id=task_id, status=TaskStatus.SUCCEEDED, capability=Capability.PAGE,
            provider_id=self.id, artifacts=[artifact],
            metrics={
                "latency_ms": round((time.time() - start) * 1000, 2),
                "total_tokens": response.total_tokens, "model": response.model,
            },
        )


SCRIPT_PROMPT = """You write podcast scripts for two hosts, A (curious) and B (expert).
Write a short engaging dialogue (8-14 exchanges) about the user's topic, in the
topic's language. Return ONLY a strict JSON object of this exact shape:
{"script": [{"speaker": "A", "line": "..."}, {"speaker": "B", "line": "..."}]}
Inside each "line", escape any double quotes as \\" and do not use raw newlines."""


class PodcastEngine(NativeEngine):
    id = "openai-podcast"
    name = "Podcast (TTS) Engine"
    capabilities = frozenset({Capability.AUDIO})
    reference = "OpenAI TTS API"

    VOICES = {"A": "alloy", "B": "onyx"}

    def __init__(
        self, store: ArtifactStore, llm_client: BaseLLMClient,
        *, model: str = "gpt-4o-mini", tts_model: str = "gpt-4o-mini-tts",
    ) -> None:
        self.store = store
        self.llm_client = llm_client
        self.model = model
        self.tts_model = tts_model

    async def _script(self, topic: str) -> list[dict[str, str]]:
        # OpenAI JSON mode guarantees parseable output; harmless to other
        # providers because we only pass it when the OpenAI SDK is present.
        kwargs: dict = {}
        if _openai_sdk(self.llm_client) is not None:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self.llm_client.achat_completion(
            [
                ChatMessage(role="system", content=SCRIPT_PROMPT),
                ChatMessage(role="user", content=topic),
            ],
            model=self.model, temperature=0.7, **kwargs,
        )
        return self._parse_script(response.content)

    @staticmethod
    def _parse_script(text: str) -> list[dict[str, str]]:
        text = (text or "").strip()
        # try object {"script": [...]}, then a bare array, then a line fallback
        for pattern in (r"\{.*\}", r"\[.*\]"):
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            script = data.get("script") if isinstance(data, dict) else data
            if isinstance(script, list):
                return [s for s in script if isinstance(s, dict) and s.get("line")]
        # last resort: parse "A: ..." / "B: ..." lines
        turns: list[dict[str, str]] = []
        for line in text.splitlines():
            m = re.match(r"\s*([AB])\s*[:：]\s*(.+)", line)
            if m:
                turns.append({"speaker": m.group(1), "line": m.group(2).strip()})
        if not turns:
            raise ValueError("Could not parse a podcast script from the model output.")
        return turns

    async def cap_podcast(self, task: TaskRequest, task_id: str) -> TaskResult:
        return await self.cap_audio(task, task_id)

    async def cap_audio(self, task: TaskRequest, task_id: str) -> TaskResult:
        sdk = _openai_sdk(self.llm_client)
        if sdk is None:
            return TaskResult(
                task_id=task_id, status=TaskStatus.FAILED, capability=Capability.AUDIO,
                provider_id=self.id, error="TTS requires an OpenAI-compatible provider.",
            )
        start = time.time()
        try:
            script = await self._script(task.prompt)
        except Exception as exc:
            return TaskResult(
                task_id=task_id, status=TaskStatus.FAILED, capability=Capability.AUDIO,
                provider_id=self.id, error=f"Script generation failed: {exc}",
            )

        loop = asyncio.get_event_loop()
        segments: list[bytes] = []
        try:
            for turn in script:
                voice = self.VOICES.get(turn.get("speaker", "A"), "alloy")
                line = turn["line"]
                audio = await loop.run_in_executor(
                    None,
                    lambda v=voice, t=line: sdk.audio.speech.create(
                        model=self.tts_model, voice=v, input=t, response_format="mp3"
                    ),
                )
                segments.append(audio.content if hasattr(audio, "content") else audio.read())
        except Exception as exc:
            return TaskResult(
                task_id=task_id, status=TaskStatus.FAILED, capability=Capability.AUDIO,
                provider_id=self.id, error=f"TTS failed: {exc}",
            )

        # mp3 frames concatenate into a playable stream — no ffmpeg dependency
        filename = f"{task_id}.mp3"
        uri = self.store.save(filename, b"".join(segments))
        transcript = "\n".join(f"{t.get('speaker','A')}: {t['line']}" for t in script)
        return TaskResult(
            task_id=task_id, status=TaskStatus.SUCCEEDED, capability=Capability.AUDIO,
            provider_id=self.id,
            artifacts=[
                Artifact(id=self.new_id("podcast"), kind="audio", title=task.prompt[:60],
                         mime_type="audio/mpeg", uri=uri,
                         metadata={"public_path": f"/artifacts/{filename}", "turns": len(script)}),
                Artifact(id=self.new_id("script"), kind="report", title="Podcast Script",
                         mime_type="text/markdown", inline=transcript),
            ],
            metrics={"latency_ms": round((time.time() - start) * 1000, 2), "turns": len(script)},
        )
