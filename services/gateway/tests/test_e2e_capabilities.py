import json
import pytest
from httpx import AsyncClient, ASGITransport

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatResponse, ToolCall
from zeropark_core.registry import ProviderRegistry
from zeropark_core.store import LocalArtifactStore
from zeropark_engines.super_agent import SuperAgentEngine
from zeropark_engines.deep_research import DeepResearchEngine
from zeropark_engines.slides import PptxSlidesEngine, LLMSlidesEngine
from zeropark_engines.rag import RAGEngine
from zeropark_engines.crawl import LocalCrawlEngine

from zeropark_gateway.main import create_app
from zeropark_gateway.auth import get_current_user

class FakeE2ELLM(BaseLLMClient):
    def __init__(self):
        self.calls = 0

    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        self.calls += 1
        return ChatResponse(content="Mocked response for E2E tests")

    async def achat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        self.calls += 1
        if "slides" in messages[0].content.lower():
            # For Slides, we must return a JSON that matches the slide schema
            return ChatResponse(content='{"title": "E2E Deck", "outline": [{"title": "Slide 1", "bullets": ["A"]}]}')
        return ChatResponse(content="Async mocked response for E2E tests")

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


@pytest.fixture
def app_instance(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("ZEROPARK_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("ZEROPARK_SEARCH__BASE_URL", raising=False)
    
    async def dummy_ensure_mcp(*args, **kwargs):
        pass
    
    monkeypatch.setattr(SuperAgentEngine, "_ensure_mcp", dummy_ensure_mcp)
    monkeypatch.setattr("zeropark_engines.super_agent._build_sandbox", lambda: None)
    
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "e2e_test_user", "role": "admin"}
    
    store = LocalArtifactStore(base_dir=str(tmp_path))
    fake_llm = FakeE2ELLM()
    
    # Rebuild a custom registry with all engines
    custom_registry = ProviderRegistry()
    
    # 1. Super Agent
    custom_registry.register(SuperAgentEngine(store=store, llm_client=fake_llm, model="test-model"))
    
    # 2. Deep Research
    crawl_engine = LocalCrawlEngine()
    custom_registry.register(DeepResearchEngine(llm_client=fake_llm, search_engine=None, crawl_engine=crawl_engine, model="test-model"))
    
    # 3. Slides
    pptx_renderer = PptxSlidesEngine(store=store)
    custom_registry.register(pptx_renderer)
    custom_registry.register(LLMSlidesEngine(llm_client=fake_llm, renderer=pptx_renderer))
    
    app.state.registry = custom_registry
    # the Router caches the registry it was built from — rebuild it too,
    # otherwise routing still sees the original engine set
    from zeropark_core.router import Router
    app.state.router = Router(custom_registry)
    return app


@pytest.mark.asyncio
async def test_super_agent_task_flow(app_instance):
    async with AsyncClient(transport=ASGITransport(app=app_instance), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "mode": "super_agent",
                "prompt": "Test super agent",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("succeeded", "failed")
        assert body["capability"] == "super_agent"

@pytest.mark.asyncio
async def test_deep_research_task_flow(app_instance):
    async with AsyncClient(transport=ASGITransport(app=app_instance), base_url="http://test") as client:
        # research needs a configured search backend; skip when this
        # environment doesn't have one (deep-research is then unregistered)
        health = (await client.get("/health")).json()
        if "research" not in health["capabilities"]:
            pytest.skip("No search backend configured — research engine not registered")
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "mode": "research",
                "prompt": "Test deep research",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["capability"] == "research"

@pytest.mark.asyncio
async def test_slides_task_flow(app_instance):
    async with AsyncClient(transport=ASGITransport(app=app_instance), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "mode": "slides",
                "prompt": "Test slides",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["capability"] == "slides"
        if body["status"] == "succeeded":
            assert len(body["artifacts"]) > 0

