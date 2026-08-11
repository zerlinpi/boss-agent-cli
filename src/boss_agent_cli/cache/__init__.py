"""Shared cache package bootstrap."""

from boss_agent_cli.cache.recovery import install_cache_recovery
from boss_agent_cli.cache.row_safety import CacheRowCorruptionError, install_cache_row_safety
from boss_agent_cli.cache.store import CacheStore

install_cache_recovery(CacheStore)
install_cache_row_safety(CacheStore)

__all__ = ["CacheRowCorruptionError", "CacheStore"]
