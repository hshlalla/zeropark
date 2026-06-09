"""Deprecated shim. Configuration lives in `zeropark_core.config`."""

from __future__ import annotations

from zeropark_core.config import LLMConfig, SearchConfig, ZeroparkSettings

__all__ = ["LLMConfig", "SearchConfig", "ZeroparkSettings"]
