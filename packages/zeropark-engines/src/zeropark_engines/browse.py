"""BROWSE — drive a real browser to load JS-heavy pages, capture screenshots and text. Native (Playwright).

Design reference: browser-use (MIT). No browser-use code or service is used.
This is the foundational headless browser engine that LLM Agents can use to interact with dynamic web pages.
"""

from __future__ import annotations

import base64
from pathlib import Path

from zeropark_core.capabilities import Capability
from zeropark_core.models import Artifact, SourceRef, TaskRequest, TaskResult, TaskStatus

from zeropark_engines.base import NativeEngine
from zeropark_engines.crawl import html_to_markdown

# We import Playwright dynamically inside the execute method to avoid hard dependencies
# if the optional browser extra is not installed.


class PlaywrightBrowseEngine(NativeEngine):
    id = "playwright-browse"
    name = "Playwright Browser Engine"
    capabilities = frozenset({Capability.BROWSE})
    reference = "browser-use (MIT) - Foundation for LLM browser loop"

    def __init__(self, *, output_dir: str = "artifacts", timeout_ms: int = 30000) -> None:
        self.output_dir = Path(output_dir)
        self.timeout_ms = timeout_ms

    async def cap_browse(self, task: TaskRequest, task_id: str) -> TaskResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                capability=Capability.BROWSE,
                provider_id=self.id,
                error="Playwright is not installed. Please install with 'pip install playwright' and run 'playwright install'.",
            )

        url = task.params.get("url") or task.prompt
        headless = str(task.params.get("headless", "true")).lower() == "true"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = self.output_dir / f"{task_id}.png"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="ZeroparkBot/0.1"
            )
            page = await context.new_page()
            
            try:
                # Go to URL and wait until network is mostly idle to ensure JS rendering
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                
                # Take screenshot
                await page.screenshot(path=str(screenshot_path), full_page=True)
                
                # Get HTML content and convert to markdown
                html_content = await page.content()
                markdown_content = html_to_markdown(html_content)
                page_title = await page.title()
                
            except Exception as e:
                await browser.close()
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    capability=Capability.BROWSE,
                    provider_id=self.id,
                    error=f"Browser action failed: {str(e)}",
                )
                
            await browser.close()

        # Create Artifacts
        artifacts = []
        
        # 1. Image Artifact
        artifacts.append(Artifact(
            id=self.new_id("screenshot"),
            kind="image",
            title=f"Screenshot of {page_title or url}",
            mime_type="image/png",
            uri=str(screenshot_path)
        ))
        
        # 2. Markdown Text Artifact
        artifacts.append(Artifact(
            id=self.new_id("page_text"),
            kind="page",
            title=f"Text of {page_title or url}",
            mime_type="text/markdown",
            inline=markdown_content,
            metadata={"chars": len(markdown_content)}
        ))

        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.BROWSE,
            provider_id=self.id,
            artifacts=artifacts,
            sources=[SourceRef(url=url, provider_id=self.id)],
            metrics={"chars": len(markdown_content)},
        )
