from __future__ import annotations

import asyncio

import pytest

from zeropark_core.capabilities import Capability
from zeropark_core.errors import NoProviderForCapability
from zeropark_core.models import TaskRequest
from zeropark_core.registry import ProviderRegistry
from zeropark_core.router import Router

from _fakes import FakeProvider


def _registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(FakeProvider("deerflow", {Capability.RESEARCH}))
    reg.register(FakeProvider("searxng", {Capability.SEARCH}))
    reg.register(FakeProvider("other-search", {Capability.SEARCH}))
    return reg


def test_plan_lists_pipeline() -> None:
    router = Router(_registry())
    plan = router.plan("research")
    assert plan.primary == Capability.RESEARCH
    assert plan.pipeline == (Capability.SEARCH, Capability.CRAWL, Capability.RESEARCH)


def test_select_honors_preference_then_registration_order() -> None:
    reg = _registry()
    router = Router(reg, preferences={"search": ["other-search"]})
    assert router.select(Capability.SEARCH).id == "other-search"
    # explicit pin beats preference
    assert router.select(Capability.SEARCH, prefer="searxng").id == "searxng"
    # no preference -> first registered
    assert Router(reg).select(Capability.SEARCH).id == "searxng"


def test_resolve_skips_capabilities_without_provider() -> None:
    # No CRAWL provider registered; research mode should still resolve the rest.
    router = Router(_registry())
    resolved = router.resolve("research")
    assert set(resolved) == {Capability.SEARCH, Capability.RESEARCH}
    assert resolved[Capability.RESEARCH].id == "deerflow"


def test_select_raises_when_capability_unavailable() -> None:
    router = Router(ProviderRegistry())
    with pytest.raises(NoProviderForCapability):
        router.select(Capability.SLIDES)


def test_unknown_mode_raises() -> None:
    with pytest.raises(KeyError):
        Router(_registry()).plan("nope")


def test_execute_dispatches_to_capability_handler() -> None:
    provider = FakeProvider("searxng", {Capability.SEARCH})
    task = TaskRequest(prompt="hi", capability=Capability.SEARCH)
    result = asyncio.run(provider.execute(task, task_id="t1"))
    assert result.provider_id == "searxng"
    assert result.status.value == "succeeded"


def test_assistant_mode_is_registered():
    router = Router(ProviderRegistry())
    plan = router.plan("assistant")
    assert plan.primary == Capability.ASSISTANT
    assert plan.pipeline == (Capability.ASSISTANT,)


def test_assistant_capability_value():
    assert Capability.ASSISTANT.value == "assistant"
