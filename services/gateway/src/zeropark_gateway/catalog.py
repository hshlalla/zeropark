"""OSS reference catalog (design references only, NOT runtime services).

Each entry records an OSS project we STUDIED while building the corresponding
native engine, plus its license and whether attribution is required. Shown on a
credits/NOTICES screen. Nothing here is run or called at runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OSSReference:
    id: str
    name: str
    references_capability: str
    repo: str
    license: str
    attribution_required: bool
    copy_allowed: bool  # may we copy source (with attribution)? False for AGPL/restricted
    notes: str = ""


REFERENCE_CATALOG: tuple[OSSReference, ...] = (
    OSSReference("deer-flow", "ByteDance DeerFlow", "research / super_agent",
                 "https://github.com/bytedance/deer-flow", "MIT", True, True,
                 "Reference for multi-agent orchestration."),
    OSSReference("crawl4ai", "Crawl4AI", "crawl",
                 "https://github.com/unclecode/crawl4ai", "Apache-2.0 + attribution", True, True,
                 "Reference for LLM-ready markdown extraction."),
    OSSReference("presenton", "Presenton", "slides",
                 "https://github.com/presenton/presenton", "Apache-2.0", True, True,
                 "Reference for prompt-to-deck generation."),
    OSSReference("browser-use", "browser-use", "browse",
                 "https://github.com/browser-use/browser-use", "MIT", True, True,
                 "Reference for LLM browser automation."),
    OSSReference("dify", "Dify", "workflow",
                 "https://github.com/langgenius/dify", "Dify Open Source License", False, False,
                 "Restricted license: reimplement independently. Do NOT copy source."),
    OSSReference("searxng", "SearXNG", "search",
                 "https://github.com/searxng/searxng", "AGPL-3.0", False, False,
                 "AGPL network copyleft: do NOT copy source. Use commodity search API instead."),
)


def get_reference_catalog() -> list[dict[str, object]]:
    return [asdict(ref) for ref in REFERENCE_CATALOG]


def reference_by_id(ref_id: str) -> OSSReference:
    for ref in REFERENCE_CATALOG:
        if ref.id == ref_id:
            return ref
    raise KeyError(ref_id)
