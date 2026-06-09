from __future__ import annotations

from zeropark_core.capabilities import Capability

from zeropark_engines.loader import build_registry


def test_base_install_registers_native_engines() -> None:
    registry = build_registry(output_dir="artifacts")
    ids = {p.id for p in registry.all()}
    assert ids == {"local-crawl", "pptx-slides"}
    assert {p.id for p in registry.for_capability(Capability.CRAWL)} == {"local-crawl"}
    assert {p.id for p in registry.for_capability(Capability.SLIDES)} == {"pptx-slides"}


def test_search_registered_only_when_configured() -> None:
    registry = build_registry(search={"base_url": "https://api.example.com/search"})
    assert {p.id for p in registry.for_capability(Capability.SEARCH)} == {"web-search"}
