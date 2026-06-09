import asyncio
from typing import List, Optional

from zeropark_core.capabilities import Capability
from zeropark_core.models import Artifact, SourceRef, TaskRequest, TaskResult, TaskStatus
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.tools import ToolRegistry

from zeropark_engines.base import NativeEngine
from zeropark_engines.tools import SearchTool, CrawlTool

class ResearchEngine(NativeEngine):
    id = "research"
    name = "Research / Super Agent"
    capabilities = frozenset({Capability.RESEARCH, Capability.SUPER_AGENT})
    reference = "DeerFlow (MIT) - Planning and citation workflow"

    def __init__(
        self,
        llm_client: BaseLLMClient,
        search_engine: NativeEngine,
        crawl_engine: NativeEngine,
        model_name: str = "gpt-4o-mini" # or any compatible model
    ) -> None:
        self.llm_client = llm_client
        self.model_name = model_name
        self.registry = ToolRegistry()
        
        self.search_tool = SearchTool(search_engine)
        self.crawl_tool = CrawlTool(crawl_engine)
        self.registry.register(self.search_tool)
        self.registry.register(self.crawl_tool)

    async def _extract_queries(self, prompt: str) -> List[str]:
        system_msg = ChatMessage(
            role="system",
            content="You are an expert researcher. Extract 1 to 3 targeted search queries based on the user's prompt. Return ONLY the queries separated by commas, no other text."
        )
        user_msg = ChatMessage(role="user", content=prompt)
        
        # This could be sync depending on the llm_client implementation, 
        # but typical LLM calls are I/O bound. Assuming synchronous call as per our simple LLMClient definition.
        # If we need async, we'd wrap it in run_in_executor. 
        # For simplicity in this native spine, we'll call it directly (blocking), 
        # or we could make chat_completion async in the future.
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.llm_client.chat_completion([system_msg, user_msg], self.model_name)
        )
        
        text = response.content.strip()
        return [q.strip() for q in text.split(",") if q.strip()]

    async def _generate_report(self, prompt: str, contexts: List[dict]) -> str:
        context_text = ""
        for i, ctx in enumerate(contexts):
            context_text += f"\n--- Source [{i+1}]: {ctx['url']} ---\n{ctx['content'][:2000]}\n" # Trim to save tokens

        system_msg = ChatMessage(
            role="system",
            content=(
                "You are an expert report writer. Write a comprehensive markdown report answering the user's prompt based on the provided sources. "
                "You MUST include inline citations like [1], [2] referencing the source index whenever you use information from a source. "
                "Include a 'References' section at the end with the URLs."
            )
        )
        user_msg = ChatMessage(role="user", content=f"Prompt: {prompt}\n\nSources Context:{context_text}")
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.llm_client.chat_completion([system_msg, user_msg], self.model_name, temperature=0.3)
        )
        return response.content

    async def cap_research(self, task: TaskRequest, task_id: str) -> TaskResult:
        # 1. Plan queries
        queries = await self._extract_queries(task.prompt)
        if not queries:
            queries = [task.prompt]
            
        all_sources: List[SourceRef] = []
        
        # 2. Search
        for query in queries[:2]: # Limit to 2 queries to avoid massive latency
            sources = await self.search_tool.execute(query=query, limit=3)
            all_sources.extend(sources)
            
        # Deduplicate sources by URL
        unique_urls = set()
        deduped_sources = []
        for s in all_sources:
            if s.url not in unique_urls:
                unique_urls.add(s.url)
                deduped_sources.append(s)
                
        # 3. Crawl top N sources
        contexts = []
        final_sources = []
        for idx, source in enumerate(deduped_sources[:3]): # Crawl top 3 only for speed
            content = await self.crawl_tool.execute(url=source.url)
            if content:
                contexts.append({
                    "url": source.url,
                    "content": content
                })
                # We record the source to send back
                final_sources.append(source)

        # 4. Generate Report
        report_markdown = await self._generate_report(task.prompt, contexts)

        artifact = Artifact(
            id=self.new_id("report"),
            kind="page",
            title=f"Research: {task.prompt[:20]}...",
            mime_type="text/markdown",
            inline=report_markdown,
        )

        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.RESEARCH,
            provider_id=self.id,
            artifacts=[artifact],
            sources=final_sources,
            metrics={"queries_executed": len(queries), "sources_crawled": len(contexts)},
        )
