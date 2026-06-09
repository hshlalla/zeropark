"""Provider = one integrated engine, behind one stable interface.

Design goals (these directly serve "add features forever without spaghetti"):

  * A provider declares the capabilities it supports as data (`capabilities`),
    not as branches in some central switch.
  * Execution dispatches by convention to `cap_<capability>` handlers. To teach
    an engine a new capability you ADD one method and ADD the capability to the
    set — you never edit a router/dispatcher elsewhere.
  * The base owns nothing engine-specific. Adapters (in zeropark-adapters)
    subclass this; HTTP plumbing lives in the adapters' own base, not here, so
    `zeropark-core` stays dependency-light and engine-agnostic.

A capability handler has the signature:

    async def cap_<name>(self, task: TaskRequest, task_id: str) -> TaskResult
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Callable, Awaitable

from zeropark_core.capabilities import Capability
from zeropark_core.errors import CapabilityNotImplemented, CapabilityNotSupported
from zeropark_core.models import ProviderHealth, RunEvent, TaskRequest, TaskResult

CapabilityHandler = Callable[[TaskRequest, str], Awaitable[TaskResult]]


class Provider(ABC):
    """Base class every engine adapter implements.

    Subclasses MUST set `id`, `name`, and `capabilities`, and implement a
    `cap_<value>` coroutine for each capability they advertise.
    """

    id: str
    name: str
    capabilities: frozenset[Capability]

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def _handler_for(self, capability: Capability) -> CapabilityHandler:
        if not self.supports(capability):
            raise CapabilityNotSupported(self.id, capability)
        handler = getattr(self, f"cap_{capability.value}", None)
        if handler is None or not callable(handler):
            raise CapabilityNotImplemented(self.id, capability)
        return handler  # type: ignore[return-value]

    async def execute(self, task: TaskRequest, *, task_id: str) -> TaskResult:
        """Run a task by dispatching to the matching capability handler."""
        handler = self._handler_for(task.capability)
        return await handler(task, task_id)

    async def stream(self, task: TaskRequest, *, task_id: str) -> AsyncIterator[RunEvent]:
        """Default streaming: run, replay collected events, then emit `done`.

        Adapters that can stream natively should override this to yield events as
        they happen.
        """
        yield RunEvent(
            type="status",
            task_id=task_id,
            provider_id=self.id,
            message="started",
            data={"capability": task.capability.value},
        )
        result = await self.execute(task, task_id=task_id)
        for event in result.events:
            yield event
        for artifact in result.artifacts:
            yield RunEvent(
                type="artifact",
                task_id=task_id,
                provider_id=self.id,
                data={"artifact": artifact.model_dump(mode="json")},
            )
        yield RunEvent(
            type="done",
            task_id=task_id,
            provider_id=self.id,
            data={"status": result.status.value, "result": result.model_dump(mode="json")},
        )

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Cheap liveness/readiness probe for /health and provider selection."""
        raise NotImplementedError
