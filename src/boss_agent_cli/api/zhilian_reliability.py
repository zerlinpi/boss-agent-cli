"""Reliability guards for the independently implemented Zhilian HTTP client."""

from __future__ import annotations

import random
import time
from typing import Any, Callable

import httpx

_INSTALLED = False
_MAX_RETRIES = 3


def install_zhilian_reliability(client_cls: type[Any]) -> None:
	"""Harden auth input, response envelopes, and CSRF-aware retry behavior."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	original_get_client: Callable[..., httpx.Client] = client_cls._get_client

	def get_client(self: Any) -> httpx.Client:
		if self._client is None:
			token = self._auth.get_token()
			cookies = token.get("cookies") if isinstance(token, dict) else None
			if not isinstance(cookies, dict):
				raise RuntimeError("智联本地登录态损坏：cookies 不是对象，请重新登录")
			if not any(isinstance(name, str) and str(value).strip() for name, value in cookies.items()):
				raise RuntimeError("智联本地登录态缺少有效 Cookie，请重新登录")
		return original_get_client(self)

	def refresh_auth(self: Any, extra_headers: dict[str, str]) -> None:
		self._auth.force_refresh(cdp_url=self._cdp_url)
		self._client = None
		self._csrf_token = None
		if "csrf-token" in extra_headers:
			extra_headers["csrf-token"] = self.get_csrf_token(force_refresh=True)

	def request(self: Any, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
		raw_headers = kwargs.pop("headers", {})
		if raw_headers is None:
			raw_headers = {}
		if not isinstance(raw_headers, dict):
			raise TypeError("智联请求 headers 必须是对象")
		extra_headers = {str(key): str(value) for key, value in raw_headers.items()}

		for attempt in range(_MAX_RETRIES + 1):
			client = self._get_client()
			self._throttle.wait()
			headers = {**self._headers_for(url), **extra_headers}
			resp = client.request(method, url, headers=headers, **kwargs)
			self._throttle.mark()
			self._merge_cookies(resp)

			status_code = resp.status_code
			if status_code in (401, 403) and attempt < _MAX_RETRIES:
				backoff = (2**attempt) + random.uniform(0.3, 0.9)
				time.sleep(backoff)
				refresh_auth(self, extra_headers)
				continue
			if status_code == 429 and attempt < _MAX_RETRIES:
				time.sleep(min(30, 5 * (2**attempt)))
				continue

			resp.raise_for_status()
			try:
				data = resp.json()
			except (ValueError, TypeError) as exc:
				raise RuntimeError("智联响应格式异常：返回内容不是有效 JSON") from exc
			if not isinstance(data, dict):
				raise RuntimeError("智联响应格式异常：期望 JSON object")
			code = data.get("code")
			if code in (401, 403) and attempt < _MAX_RETRIES:
				backoff = (2**attempt) + random.uniform(0.3, 0.9)
				time.sleep(backoff)
				refresh_auth(self, extra_headers)
				continue
			if code == 429 and attempt < _MAX_RETRIES:
				time.sleep(min(30, 5 * (2**attempt)))
				continue
			return data

		raise RuntimeError("智联请求失败，已达最大重试次数")

	setattr(client_cls, "_get_client", get_client)
	setattr(client_cls, "_request", request)
