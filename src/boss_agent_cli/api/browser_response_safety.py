"""Return-contract guard for browser-backed BOSS API requests."""

from __future__ import annotations

from typing import Any, Callable


def install_browser_response_safety(session_cls: type[Any]) -> None:
	"""Require BrowserSession.request to return a JSON object on every transport."""
	if getattr(session_cls, "_boss_response_safety_installed", False):
		return
	original_request: Callable[..., Any] = session_cls.request

	def request(self: Any, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
		result = original_request(self, method, url, **kwargs)
		if not isinstance(result, dict):
			raise RuntimeError("浏览器通道返回格式异常：期望 JSON object")
		return result

	setattr(session_cls, "request", request)
	setattr(session_cls, "_boss_response_safety_installed", True)
