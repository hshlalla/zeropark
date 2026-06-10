"""BROWSER AGENT — LLM-driven browser control loop (design ref: browser-use, MIT).

Where `PlaywrightBrowseEngine` loads ONE page and captures it, this engine lets
the LLM operate the browser like a person: look at the page's interactive
elements, then navigate / click / type / scroll repeatedly until the task is
done. This is the capability gap between "screenshot a page" and "log in to the
portal, find the invoice, and read me the total".

No browser-use code is used; elements are indexed via a small DOM script and
actions are chosen with native LLM tool calling.
"""

from __future__ import annotations

import json
from typing import Any

from zeropark_core import ArtifactStore
from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.models import Artifact, SourceRef, TaskRequest, TaskResult, TaskStatus
from zeropark_core.netguard import validate_public_url
from zeropark_engines.base import NativeEngine

DEFAULT_MAX_STEPS = 15

# Collect visible interactive elements, tag each with a zp-index attribute the
# agent can reference in click/type actions.
_SNAPSHOT_JS = """
() => {
  const selectors = 'a, button, input, select, textarea, [role="button"], [onclick]';
  const elements = [];
  let index = 0;
  for (const el of document.querySelectorAll(selectors)) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    el.setAttribute('data-zp-index', String(index));
    elements.push({
      index: index,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      text: (el.innerText || el.value || el.getAttribute('placeholder') || el.getAttribute('aria-label') || '').trim().slice(0, 80),
      href: el.getAttribute('href') || ''
    });
    index += 1;
    if (index >= 120) break;
  }
  return elements;
}
"""

SYSTEM_PROMPT = """You are a browser automation agent. You see the current page's
URL, title, visible text excerpt, and a numbered list of interactive elements.
Choose ONE action per step using the provided tools. Be efficient: do not revisit
pages you have already seen. When the task is complete (or impossible), call
`finish` with your answer."""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Go to a URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click the interactive element with the given index.",
            "parameters": {
                "type": "object",
                "properties": {"index": {"type": "integer"}},
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the element with the given index (input/textarea). Optionally press Enter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                    "press_enter": {"type": "boolean"},
                },
                "required": ["index", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the page down (or up) by one viewport.",
            "parameters": {
                "type": "object",
                "properties": {"direction": {"type": "string", "enum": ["down", "up"]}},
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish the task and report the final answer/result.",
            "parameters": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        },
    },
]


class BrowserAgentEngine(NativeEngine):
    id = "browser-agent"
    name = "Browser Agent (LLM-driven)"
    capabilities = frozenset({Capability.BROWSE})
    reference = "browser-use (MIT) - design reference only"

    def __init__(
        self,
        store: ArtifactStore,
        llm_client: BaseLLMClient,
        *,
        model: str = "gpt-4o",
        max_steps: int = DEFAULT_MAX_STEPS,
        timeout_ms: int = 30000,
    ) -> None:
        self.store = store
        self.llm_client = llm_client
        self.model = model
        self.max_steps = max_steps
        self.timeout_ms = timeout_ms

    async def _observe(self, page) -> str:
        elements = await page.evaluate(_SNAPSHOT_JS)
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        lines = [
            f"URL: {page.url}",
            f"TITLE: {await page.title()}",
            "PAGE TEXT (excerpt):",
            text[:1500],
            "INTERACTIVE ELEMENTS:",
        ]
        for el in elements:
            label = el["text"] or el["href"]
            lines.append(f"[{el['index']}] <{el['tag']}{' type=' + el['type'] if el['type'] else ''}> {label}")
        return "\n".join(lines)

    async def _act(self, page, name: str, args: dict[str, Any]) -> str:
        if name == "navigate":
            url = args["url"]
            validate_public_url(url)
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            return f"Navigated to {url}"
        if name == "click":
            locator = page.locator(f"[data-zp-index='{args['index']}']")
            await locator.click(timeout=5000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            return f"Clicked element {args['index']}"
        if name == "type_text":
            locator = page.locator(f"[data-zp-index='{args['index']}']")
            await locator.fill(args["text"], timeout=5000)
            if args.get("press_enter"):
                await locator.press("Enter")
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
            return f"Typed into element {args['index']}"
        if name == "scroll":
            delta = "window.innerHeight" if args.get("direction", "down") == "down" else "-window.innerHeight"
            await page.evaluate(f"window.scrollBy(0, {delta})")
            return "Scrolled"
        return f"Unknown action {name}"

    async def cap_browse(self, task: TaskRequest, task_id: str) -> TaskResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                capability=Capability.BROWSE,
                provider_id=self.id,
                error="Playwright is not installed. pip install playwright && playwright install",
            )

        start_url = task.params.get("url")
        max_steps = int(task.params.get("max_steps", self.max_steps))
        visited: list[str] = []
        final_answer = ""

        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=f"Task: {task.prompt}"),
        ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800}, user_agent="ZeroparkAgent/0.1"
            )
            page = await context.new_page()
            try:
                if start_url:
                    validate_public_url(start_url)
                    await page.goto(start_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    visited.append(start_url)

                for _ in range(max_steps):
                    observation = await self._observe(page)
                    messages.append(ChatMessage(role="user", content=observation))

                    response = await self.llm_client.achat_completion(
                        messages, model=self.model, temperature=0.0, tools=_TOOLS
                    )
                    if not response.tool_calls:
                        final_answer = response.content
                        break

                    messages.append(
                        ChatMessage(
                            role="assistant",
                            content=response.content or "",
                            tool_calls=response.tool_calls,
                        )
                    )
                    finished = False
                    for tool_call in response.tool_calls:
                        try:
                            args = json.loads(tool_call.arguments) if tool_call.arguments else {}
                        except json.JSONDecodeError:
                            args = {}
                        if tool_call.name == "finish":
                            final_answer = args.get("answer", "")
                            finished = True
                            result_text = "Task finished."
                        else:
                            try:
                                result_text = await self._act(page, tool_call.name, args)
                                if tool_call.name == "navigate":
                                    visited.append(args.get("url", ""))
                            except Exception as exc:
                                result_text = f"Action failed: {exc}"
                        messages.append(
                            ChatMessage(
                                role="tool",
                                content=result_text,
                                tool_call_id=tool_call.id,
                                name=tool_call.name,
                            )
                        )
                    if finished:
                        break

                if not final_answer:
                    final_answer = "Max steps reached without finishing the task."

                screenshot = await page.screenshot(full_page=False)
                screenshot_artifact = Artifact(
                    id=self.new_id("browse_agent_shot"),
                    kind="image",
                    title="Final page screenshot",
                    mime_type="image/png",
                    uri=self.store.save(f"{task_id}_final.png", screenshot),
                    metadata={"url": page.url},
                )
            finally:
                await browser.close()

        report = Artifact(
            id=self.new_id("browse_agent"),
            kind="report",
            title="Browser Agent Result",
            mime_type="text/markdown",
            inline=final_answer,
            metadata={"visited": visited},
        )
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.BROWSE,
            provider_id=self.id,
            artifacts=[report, screenshot_artifact],
            sources=[SourceRef(url=u, provider_id=self.id) for u in visited if u],
            metrics={"steps": len([m for m in messages if m.role == "tool"]), "model": self.model},
        )
