"""Capabilities = the stable product vocabulary.

A capability is a thing the workspace can do, named independently of which OSS
engine happens to provide it today. Product code and the web UI depend on these
names, NOT on engine identifiers. Swapping DeerFlow for another research engine,
or Dify for another workflow engine, must not require touching any code that
references a Capability.

To add a new capability: add a member here, add a `cap_<value>` handler on the
providers that support it, and add/extend a ModePlan in router.py. No existing
code needs editing.
"""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    SEARCH = "search"          # metasearch / web results
    CRAWL = "crawl"            # fetch + extract a URL to clean markdown/structured data
    RESEARCH = "research"      # multi-step research with citations
    SLIDES = "slides"          # generate a deck (pptx/pdf)
    SHEETS = "sheets"          # generate a spreadsheet (xlsx)
    DASHBOARD = "dashboard"    # generate a live data dashboard/page
    BROWSE = "browse"          # drive a real browser to complete a web task
    WORKFLOW = "workflow"      # run a configured workflow / RAG app
    SUPER_AGENT = "super_agent"  # long-horizon planning across many tools

    def __str__(self) -> str:  # so f"{cap}" renders the value, not "Capability.X"
        return self.value
