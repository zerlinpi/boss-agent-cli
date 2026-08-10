"""Shared API package bootstrap."""

from boss_agent_cli.api.browser_client import BrowserSession
from boss_agent_cli.api.browser_response_safety import install_browser_response_safety
from boss_agent_cli.api.zhilian_client import ZhilianClient
from boss_agent_cli.api.zhilian_reliability import install_zhilian_reliability

install_browser_response_safety(BrowserSession)
install_zhilian_reliability(ZhilianClient)

__all__ = []
