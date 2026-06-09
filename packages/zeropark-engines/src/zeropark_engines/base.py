"""NativeEngine: base for capabilities implemented IN-PROCESS.

Unlike HTTP adapters, a NativeEngine does the work itself using lightweight,
permissively-licensed libraries. The OSS projects (DeerFlow, Dify, Crawl4AI,
Presenton, browser-use) are DESIGN REFERENCES ONLY — studied, not imported and
not called over the network. This keeps the framework a single, self-contained,
sellable artifact with one dependency set.

`reference` records which OSS inspired an engine, for the NOTICES file. Copying
source is only acceptable from MIT/Apache engines (with attribution); Dify and
SearXNG (AGPL) must be reimplemented independently.
"""

from __future__ import annotations

import uuid

from zeropark_core.models import ProviderHealth
from zeropark_core.provider import Provider


class NativeEngine(Provider):
    id = "native"
    name = "Native Engine"
    capabilities = frozenset()
    reference: str = ""

    @staticmethod
    def new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.id, ok=True, detail="native")
