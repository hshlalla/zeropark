import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from zeropark_core.models import TaskRequest, TaskStatus
from zeropark_engines.research import ResearchEngine
from zeropark_core.llm import BaseLLMClient, ChatResponse, ChatMessage

class MockLLMClient(BaseLLMClient):
    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, **kwargs):
        if "expert researcher" in messages[0].content:
            return ChatResponse(content="AI trends, Machine Learning")
        else:
            return ChatResponse(content="# AI Report\n\nAI is growing [1].\n\nReferences:\n[1] http://test.com")

@pytest.mark.asyncio
async def test_research_engine_flow():
    mock_search = MagicMock()
    mock_search_result = MagicMock()
    mock_source = MagicMock()
    mock_source.url = "http://test.com"
    mock_search_result.sources = [mock_source]
    mock_search.cap_search = AsyncMock(return_value=mock_search_result)
    
    mock_crawl = MagicMock()
    mock_crawl_result = MagicMock()
    mock_artifact = MagicMock()
    mock_artifact.inline = "This is a crawl text about AI."
    mock_crawl_result.artifacts = [mock_artifact]
    mock_crawl.cap_crawl = AsyncMock(return_value=mock_crawl_result)
    
    llm = MockLLMClient()
    
    engine = ResearchEngine(llm_client=llm, search_engine=mock_search, crawl_engine=mock_crawl)
    
    req = TaskRequest(prompt="What is the trend in AI?")
    result = await engine.cap_research(req, "task-123")
    
    assert result.status == TaskStatus.SUCCEEDED
    assert len(result.artifacts) == 1
    assert "AI Report" in result.artifacts[0].inline
    assert len(result.sources) == 1
    assert result.sources[0].url == "http://test.com"
