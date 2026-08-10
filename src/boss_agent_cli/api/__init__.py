"""Shared API package bootstrap."""

from boss_agent_cli.api.zhilian_client import ZhilianClient
from boss_agent_cli.api.zhilian_reliability import install_zhilian_reliability

install_zhilian_reliability(ZhilianClient)

__all__ = []
