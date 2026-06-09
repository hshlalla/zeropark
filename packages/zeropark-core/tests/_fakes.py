"""Tiny in-memory provider for testing the spine without any engine or network."""

from __future__ import annotations

from zeropark_core.capabilities import Capability
from zeropark_core.models import ProviderHealth, TaskRequest, TaskResult, TaskStatus
from zeropark_core.provider import Provider


class FakeProvider(Provider):
    def __init__(self, provider_id: str, caps: set[Capability]) -> None:
        self.id = provider_id
        self.name = f"Fake {provider_id}"
        self.capabilities = frozenset(caps)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.id, ok=True)

    async def cap_search(self, task: TaskRequest, task_id: str) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.SEARCH,
            provider_id=self.id,
        )

    async def cap_research(self, task: TaskRequest, task_id: str) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.RESEARCH,
            provider_id=self.id,
        )
