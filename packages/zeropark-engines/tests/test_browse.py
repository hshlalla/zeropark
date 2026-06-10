import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from zeropark_core.models import TaskRequest, TaskStatus
from zeropark_core.store import LocalArtifactStore
from zeropark_engines.browse import PlaywrightBrowseEngine

from zeropark_core.capabilities import Capability

@pytest.mark.asyncio
async def test_browse_engine_flow(tmp_path, monkeypatch):
    # The fetch is mocked, so skip the SSRF DNS resolution in this offline test.
    monkeypatch.setenv("ZEROPARK_ALLOW_PRIVATE_URLS", "1")
    store = LocalArtifactStore(base_dir=str(tmp_path))
    engine = PlaywrightBrowseEngine(store=store)
    req = TaskRequest(prompt="http://test.com", capability=Capability.CRAWL, params={"headless": True})
    
    # Mocking playwright.async_api.async_playwright
    mock_async_playwright = MagicMock()
    mock_playwright_context = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    
    mock_page.content = AsyncMock(return_value="<html><body><h1>Test Page</h1></body></html>")
    mock_page.title = AsyncMock(return_value="Test Title")
    mock_page.screenshot = AsyncMock(return_value=b"fake image bytes")
    
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_playwright_context.chromium.launch = AsyncMock(return_value=mock_browser)
    
    # Setup context manager for async_playwright
    mock_async_playwright.return_value.__aenter__ = AsyncMock(return_value=mock_playwright_context)
    mock_async_playwright.return_value.__aexit__ = AsyncMock()
    
    with patch("playwright.async_api.async_playwright", mock_async_playwright):
        result = await engine.cap_browse(req, "test-browse-1")
    
    assert result.status == TaskStatus.SUCCEEDED
    assert len(result.artifacts) == 2
    assert result.artifacts[0].kind == "image"
    assert result.artifacts[1].kind == "page"
    assert "Test Page" in result.artifacts[1].inline
    
    # Assert playwright was called correctly
    mock_playwright_context.chromium.launch.assert_called_once_with(headless=True)
    mock_page.goto.assert_called_once_with("http://test.com", wait_until="networkidle", timeout=30000)
    mock_page.screenshot.assert_called_once()
    mock_browser.close.assert_called_once()
