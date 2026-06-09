from __future__ import annotations

import pytest

from zeropark_core.capabilities import Capability
from zeropark_core.errors import ProviderNotConfigured
from zeropark_core.registry import ProviderRegistry

from _fakes import FakeProvider


def test_register_and_lookup() -> None:
    reg = ProviderRegistry()
    reg.register(FakeProvider("a", {Capability.SEARCH}))
    assert "a" in reg
    assert len(reg) == 1
    assert reg.get("a").id == "a"


def test_for_capability_filters_and_orders() -> None:
    reg = ProviderRegistry()
    reg.register(FakeProvider("a", {Capability.SEARCH}))
    reg.register(FakeProvider("b", {Capability.SEARCH, Capability.RESEARCH}))
    reg.register(FakeProvider("c", {Capability.RESEARCH}))
    assert [p.id for p in reg.for_capability(Capability.SEARCH)] == ["a", "b"]
    assert [p.id for p in reg.for_capability(Capability.RESEARCH)] == ["b", "c"]
    assert reg.capabilities() == {Capability.SEARCH, Capability.RESEARCH}


def test_duplicate_registration_rejected() -> None:
    reg = ProviderRegistry()
    reg.register(FakeProvider("a", {Capability.SEARCH}))
    with pytest.raises(ValueError):
        reg.register(FakeProvider("a", {Capability.SEARCH}))


def test_missing_provider_raises() -> None:
    reg = ProviderRegistry()
    with pytest.raises(ProviderNotConfigured):
        reg.get("nope")
