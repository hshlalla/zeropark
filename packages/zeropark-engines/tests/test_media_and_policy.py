"""P3: browser domain allowlist, PAGE engine, podcast script parsing."""

import json

import pytest

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatResponse
from zeropark_core.models import TaskRequest, TaskStatus
from zeropark_core.store import LocalArtifactStore
from zeropark_engines.browser_agent import domain_allowed
from zeropark_engines.media import PageEngine, PodcastEngine


def test_domain_allowlist(monkeypatch):
    monkeypatch.delenv("ZEROPARK_BROWSER_ALLOWED_DOMAINS", raising=False)
    assert domain_allowed("https://anything.example.com/x")  # unset = unrestricted

    monkeypatch.setenv("ZEROPARK_BROWSER_ALLOWED_DOMAINS", "samsung.com, lge.co.kr")
    assert domain_allowed("https://samsung.com/support")
    assert domain_allowed("https://mail.samsung.com/inbox")      # subdomain ok
    assert not domain_allowed("https://evil-samsung.com/")       # suffix trick blocked
    assert not domain_allowed("https://google.com/")


class PageLLM(BaseLLMClient):
    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        return ChatResponse(
            content="```html\n<!DOCTYPE html><html><body><h1>Landing</h1></body></html>\n```",
            model=model,
        )

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
async def test_page_engine_writes_html_artifact(tmp_path):
    store = LocalArtifactStore(base_dir=str(tmp_path))
    engine = PageEngine(store=store, llm_client=PageLLM(), model="m")
    task = TaskRequest(prompt="제품 소개 랜딩페이지", capability=Capability.PAGE)

    result = await engine.cap_page(task, "t1")
    assert result.status == TaskStatus.SUCCEEDED
    artifact = result.artifacts[0]
    assert artifact.kind == "page"
    assert artifact.metadata["public_path"].startswith("/artifacts/")
    html = open(artifact.uri, encoding="utf-8").read()
    # markdown fences are stripped — file starts with the doctype
    assert html.startswith("<!DOCTYPE html") and "<h1>Landing</h1>" in html


class ScriptLLM(BaseLLMClient):
    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        return ChatResponse(content=json.dumps({"script": [
            {"speaker": "A", "line": "오늘 주제는 AI 에이전트!"},
            {"speaker": "B", "line": "네, 핵심은 도구 사용이죠."},
        ]}))

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
async def test_podcast_script_parsing(tmp_path):
    store = LocalArtifactStore(base_dir=str(tmp_path))
    engine = PodcastEngine(store=store, llm_client=ScriptLLM())
    script = await engine._script("AI agents")
    assert len(script) == 2 and script[0]["speaker"] == "A"


def test_podcast_parse_fallbacks():
    # object schema
    assert len(PodcastEngine._parse_script('{"script":[{"speaker":"A","line":"hi"}]}')) == 1
    # bare array
    assert len(PodcastEngine._parse_script('[{"speaker":"B","line":"yo"}]')) == 1
    # line-based fallback when JSON is unrecoverable
    fallback = PodcastEngine._parse_script("A: 안녕하세요\nB: 반갑습니다")
    assert [t["speaker"] for t in fallback] == ["A", "B"]


@pytest.mark.asyncio
async def test_podcast_without_openai_sdk_fails_cleanly(tmp_path):
    store = LocalArtifactStore(base_dir=str(tmp_path))
    engine = PodcastEngine(store=store, llm_client=ScriptLLM())  # no .client attr
    task = TaskRequest(prompt="topic", capability=Capability.AUDIO)
    result = await engine.cap_audio(task, "t2")
    assert result.status == TaskStatus.FAILED
    assert "OpenAI" in (result.error or "")
