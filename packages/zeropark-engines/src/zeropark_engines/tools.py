from typing import Any, List
from pydantic import Field
from zeropark_core.capabilities import Capability

from zeropark_core.tools import BaseTool, ToolSpec, ToolParameter
from zeropark_core.models import TaskRequest

class SearchTool(BaseTool):
    """Tool wrapper for WebSearchEngine"""
    
    def __init__(self, search_engine):
        self.search_engine = search_engine

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="search",
            description="Searches the web for given keywords and returns top relevant URLs.",
            parameters=[
                ToolParameter(name="query", type="string", description="The search query."),
                ToolParameter(name="limit", type="integer", description="Max number of results.", required=False)
            ]
        )

    async def execute(self, query: str, limit: int = 5, **kwargs) -> Any:
        # Create a dummy TaskRequest to pass into cap_search
        task = TaskRequest(
            prompt=query,
            capability=Capability.SEARCH,
            params={"limit": limit}
        )
        # SearchEngine expects (task, task_id)
        result = await self.search_engine.cap_search(task, task_id="search_tool_internal")
        return result.sources

class CrawlTool(BaseTool):
    """Tool wrapper for LocalCrawlEngine"""
    
    def __init__(self, crawl_engine):
        self.crawl_engine = crawl_engine

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="crawl",
            description="Crawls a specific URL and returns the content in clean markdown format.",
            parameters=[
                ToolParameter(name="url", type="string", description="The URL to crawl.")
            ]
        )

    async def execute(self, url: str, **kwargs) -> Any:
        # Create a dummy TaskRequest to pass into cap_crawl
        task = TaskRequest(
            prompt="Crawl this url",
            capability=Capability.CRAWL,
            params={"url": url}
        )
        result = await self.crawl_engine.cap_crawl(task, task_id="crawl_tool_internal")
        if result.artifacts and len(result.artifacts) > 0:
            return result.artifacts[0].inline
        return ""
