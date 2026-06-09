import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from zeropark_core.models import TaskRequest, TaskResult, TaskStatus
from zeropark_engines.sheets import LLMSheetsEngine
from zeropark_core.llm import BaseLLMClient, ChatResponse

class MockLLMClientForSheets(BaseLLMClient):
    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, **kwargs):
        json_str = '''
        {
            "headers": ["Item", "Cost"],
            "rows": [["A", 10], ["B", 20], ["Total", "=SUM(B2:B3)"]]
        }
        '''
        return ChatResponse(content=json_str)

@pytest.mark.asyncio
async def test_llm_sheets_engine_flow():
    mock_renderer = MagicMock()
    mock_result = TaskResult(
        task_id="test-sheets-1",
        status=TaskStatus.SUCCEEDED,
        capability="sheets",
        provider_id="openpyxl-sheets",
        artifacts=[]
    )
    mock_renderer.cap_sheets = AsyncMock(return_value=mock_result)
    
    llm = MockLLMClientForSheets()
    engine = LLMSheetsEngine(llm_client=llm, renderer=mock_renderer)
    
    req = TaskRequest(prompt="Make a cost table")
    result = await engine.cap_sheets(req, "test-sheets-1")
    
    # Assert LLM was used to inject sheet_data into params
    assert req.params is not None
    assert "sheet_data" in req.params
    assert "headers" in req.params["sheet_data"]
    assert len(req.params["sheet_data"]["rows"]) == 3
    assert req.params["sheet_data"]["rows"][2][1] == "=SUM(B2:B3)"
    
    # Assert renderer was called
    mock_renderer.cap_sheets.assert_called_once()
    assert result.status == TaskStatus.SUCCEEDED
