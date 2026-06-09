"""Router: maps a product *mode* to capabilities, then to concrete providers.

Two separations of concern live here, and they matter for long-term cleanliness:

  1. mode -> capabilities (ModePlan): what a user-facing mode like "research"
     actually needs (search, then crawl, then research). This is product policy.

  2. capability -> provider (select/resolve): which engine serves a capability
     in THIS deployment. This is configuration (registry + preferences).

Business logic and the web UI speak in modes and capabilities. Engine ids appear
only in `preferences` config and inside adapters. Add a mode = add a ModePlan.
Re-point a capability to a different engine = change one preference list. Neither
requires touching execution code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from zeropark_core.capabilities import Capability
from zeropark_core.errors import NoProviderForCapability
from zeropark_core.provider import Provider
from zeropark_core.registry import ProviderRegistry


@dataclass(frozen=True)
class ModePlan:
    mode: str
    primary: Capability
    pipeline: tuple[Capability, ...]
    description: str = ""


# Product-level modes. Pipelines are ordered; `primary` is the headline capability.
DEFAULT_MODES: dict[str, ModePlan] = {
    "super_agent": ModePlan(
        "super_agent",
        Capability.SUPER_AGENT,
        (Capability.SUPER_AGENT,),
        "Long-horizon planning and execution across tools.",
    ),
    "research": ModePlan(
        "research",
        Capability.RESEARCH,
        (Capability.SEARCH, Capability.CRAWL, Capability.RESEARCH),
        "Deep research with citations.",
    ),
    "slides": ModePlan(
        "slides",
        Capability.SLIDES,
        (Capability.RESEARCH, Capability.SLIDES),
        "Generate an editable deck.",
    ),
    "sheets": ModePlan(
        "sheets",
        Capability.SHEETS,
        (Capability.RESEARCH, Capability.SHEETS),
        "Generate a spreadsheet.",
    ),
    "dashboard": ModePlan(
        "dashboard",
        Capability.DASHBOARD,
        (Capability.RESEARCH, Capability.DASHBOARD),
        "Generate a live data dashboard.",
    ),
    "browser": ModePlan(
        "browser",
        Capability.BROWSE,
        (Capability.BROWSE,),
        "Drive a real browser to complete a task.",
    ),
    "workflow": ModePlan(
        "workflow",
        Capability.WORKFLOW,
        (Capability.WORKFLOW,),
        "Run a configured workflow / RAG app.",
    ),
}


@dataclass
class Router:
    registry: ProviderRegistry
    modes: dict[str, ModePlan] = field(default_factory=lambda: dict(DEFAULT_MODES))
    # capability value -> ordered preferred provider ids
    preferences: dict[str, list[str]] = field(default_factory=dict)

    def plan(self, mode: str) -> ModePlan:
        try:
            return self.modes[mode]
        except KeyError as exc:
            raise KeyError(f"Unknown mode: {mode}") from exc

    def known_modes(self) -> list[str]:
        return list(self.modes.keys())

    def select(self, capability: Capability, *, prefer: str | None = None) -> Provider:
        """Pick one provider for a capability.

        Order of precedence: explicit `prefer` pin -> configured preference list
        -> first registered provider that supports it.
        """
        candidates = self.registry.for_capability(capability)
        if not candidates:
            raise NoProviderForCapability(capability)

        by_id = {p.id: p for p in candidates}
        if prefer and prefer in by_id:
            return by_id[prefer]

        for provider_id in self.preferences.get(capability.value, []):
            if provider_id in by_id:
                return by_id[provider_id]

        return candidates[0]

    def resolve(self, mode: str, *, prefer: str | None = None) -> dict[Capability, Provider]:
        """Resolve every capability in a mode's pipeline to a concrete provider.

        Capabilities with no available provider are skipped (a deployment may not
        install every engine); the caller can inspect which were resolved.
        """
        chosen: dict[Capability, Provider] = {}
        for capability in self.plan(mode).pipeline:
            try:
                chosen[capability] = self.select(
                    capability, prefer=prefer if capability == self.plan(mode).primary else None
                )
            except NoProviderForCapability:
                continue
        return chosen
