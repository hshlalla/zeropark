import sys
import os
import asyncio
from pathlib import Path

# Fix pythonpath
sys.path.insert(0, str(Path("services/gateway/src").resolve()))
sys.path.insert(0, str(Path("packages/zeropark-core/src").resolve()))
sys.path.insert(0, str(Path("packages/zeropark-engines/src").resolve()))

os.environ["ZEROPARK_MCP_CONFIG"] = "non_existent_for_test.json"
os.environ["ZEROPARK_OUTPUT_DIR"] = "tmp"

from fastapi.testclient import TestClient
from zeropark_core.llm import BaseLLMClient, ChatResponse
from zeropark_core.registry import ProviderRegistry
from zeropark_core.store import LocalArtifactStore
from zeropark_engines.super_agent import SuperAgentEngine
from zeropark_gateway.main import create_app

class FakeE2ELLM(BaseLLMClient):
    def chat_completion(self, *args, **kwargs):
        return ChatResponse(content="Mocked response")

    async def achat_completion(self, *args, **kwargs):
        return ChatResponse(content="Async mocked response")

    def create_embeddings(self, texts, *args, **kwargs):
        return [[0.0] for _ in texts]

print("Creating app...")
app = create_app()

store = LocalArtifactStore(base_dir="tmp")
fake_llm = FakeE2ELLM()

custom_registry = ProviderRegistry()
# Hack sandbox out
import zeropark_engines.super_agent
zeropark_engines.super_agent._build_sandbox = lambda: None

engine = SuperAgentEngine(store=store, llm_client=fake_llm, model="test-model")
custom_registry.register(engine)

app.state.registry = custom_registry

print("Creating TestClient...")
client = TestClient(app)

print("Posting to /api/v1/tasks...")
resp = client.post(
    "/api/v1/tasks",
    json={
        "mode": "super_agent",
        "prompt": "Test super agent",
    },
)

print("Response:", resp.status_code)
print(resp.json())
