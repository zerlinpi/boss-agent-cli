"""Shared cache package bootstrap."""

from boss_agent_cli.cache.recovery import install_cache_recovery
from boss_agent_cli.cache.store import CacheStore

install_cache_recovery(CacheStore)

__all__ = ["CacheStore"]
