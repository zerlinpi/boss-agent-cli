"""Shared hybrid HTTP client base for BOSS candidate/recruiter clients.

`BossClient` and `BossRecruiterClient` share ~90% of their request plumbing:
the httpx-channel retry loop (403/安全验证 refresh, stoken-expired refresh,
rate-limit cooldown), lazy client/browser construction, and lifecycle.
The per-platform differences (base URL / headers / referer map, auth-error
class, response codes, whether to stamp `__cli_endpoint_hint__`) are exposed
as class attributes so each subclass only sets data, not behavior.

Zhilian is intentionally NOT a subclass: its client speaks a different retry
dialect (HTTP + body 401/403/429, no stoken, CSRF bootstrap).
"""

from __future__ import annotations

import random
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any, TypeVar, cast

import httpx

from boss_agent_cli.api.httpx_helpers import (
	add_stoken_to_get_params,
	browser_headers,
	merge_response_cookies,
	referer_header,
)
from boss_agent_cli.api.throttle import RequestThrottle

if TYPE_CHECKING:
	from boss_agent_cli.api.browser_client import BrowserSession
	from boss_agent_cli.auth.manager import AuthManager

_MAX_RETRIES = 3

_SelfT = TypeVar("_SelfT", bound="_BaseHttpClient")


class _BaseHttpClient:
	"""Hybrid API client base: httpx channel for low-risk ops, browser for high-risk ops."""

	_BASE_URL: str
	_DEFAULT_HEADERS: dict[str, str]
	_REFERER_MAP: dict[str, str]
	_AUTH_ERROR_CLS: type[Exception]
	_CODE_STOKEN_EXPIRED: int
	_CODE_RATE_LIMITED: int
	_ADD_ENDPOINT_HINT: bool = False

	def __init__(
		self, auth_manager: "AuthManager", *, delay: tuple[float, float] = (1.5, 3.0), cdp_url: str | None = None
	) -> None:
		self._auth = auth_manager
		self._delay = delay
		self._client: httpx.Client | None = None
		self._browser_session: "BrowserSession | None" = None
		self._throttle = RequestThrottle(delay)
		self._cdp_url = cdp_url
		self._closed = False
		self._register()

	def _register(self) -> None:
		"""Track this instance for the atexit safeguard. Overridden per module."""

	def _unregister(self) -> None:
		"""Drop this instance from the atexit safeguard. Overridden per module."""

	def _validated_token(self) -> tuple[dict[str, Any], dict[str, str]]:
		token = self._auth.get_token()
		cookies = token.get("cookies")
		if not isinstance(cookies, dict):
			raise self._AUTH_ERROR_CLS("本地登录态损坏：cookies 不是对象，请重新登录")
		safe_cookies = {
			str(name): str(value)
			for name, value in cookies.items()
			if isinstance(name, str) and isinstance(value, (str, int, float))
		}
		if not safe_cookies:
			raise self._AUTH_ERROR_CLS("本地登录态缺少有效 Cookie，请重新登录")
		return token, safe_cookies

	def _get_client(self) -> httpx.Client:
		if self._client is None:
			token, cookies = self._validated_token()
			headers = browser_headers(self._DEFAULT_HEADERS, token)
			self._client = httpx.Client(
				base_url=self._BASE_URL,
				cookies=cookies,
				headers=headers,
				follow_redirects=True,
				timeout=30,
			)
		return self._client

	def _get_browser(self) -> "BrowserSession":
		if self._browser_session is None:
			from boss_agent_cli.api.browser_client import BrowserSession

			token, cookies = self._validated_token()
			self._browser_session = BrowserSession(
				cookies=cookies,
				user_agent=str(token.get("user_agent") or ""),
				delay=self._delay,
				cdp_url=self._cdp_url,
				logger=getattr(self._auth, "_logger", None),
			)
		return self._browser_session

	def _headers_for(self, url: str) -> dict[str, str]:
		return referer_header(url, self._REFERER_MAP, f"{self._BASE_URL}/")

	def _merge_cookies(self, resp: httpx.Response) -> None:
		merge_response_cookies(self._get_client(), resp)

	def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
		"""httpx 请求，循环重试（最多 _MAX_RETRIES 次）。"""
		raw_extra_headers = kwargs.pop("extra_headers", {})
		if not isinstance(raw_extra_headers, dict):
			raise TypeError("extra_headers 必须是字符串键值对象")
		extra_headers_override = {
			str(name): str(value)
			for name, value in raw_extra_headers.items()
			if isinstance(name, str) and isinstance(value, str)
		}
		for attempt in range(_MAX_RETRIES + 1):
			client = self._get_client()
			token = self._auth.get_token()
			stoken = str(token.get("stoken") or "")
			add_stoken_to_get_params(method, kwargs, stoken)
			self._throttle.wait()

			headers = {**self._headers_for(url), **extra_headers_override}
			resp = client.request(method, url, headers=headers, **kwargs)
			self._throttle.mark()
			self._merge_cookies(resp)

			if resp.status_code == 403 or "安全验证" in resp.text:
				if attempt >= _MAX_RETRIES:
					raise self._AUTH_ERROR_CLS("Token 刷新后仍被拒绝，请重新登录")
				backoff = (2**attempt) + random.uniform(0.5, 1.5)
				time.sleep(backoff)
				self._auth.force_refresh(cdp_url=self._cdp_url)
				self._client = None
				continue

			resp.raise_for_status()
			try:
				raw_data = resp.json()
			except (ValueError, TypeError) as exc:
				raise self._AUTH_ERROR_CLS("平台返回无法解析的 JSON 响应，请稍后重试") from exc
			if not isinstance(raw_data, dict):
				raise self._AUTH_ERROR_CLS("平台返回了非对象 JSON 响应，请稍后重试")
			data = cast("dict[str, Any]", raw_data)
			code = data.get("code")

			if code == self._CODE_STOKEN_EXPIRED and attempt < _MAX_RETRIES:
				backoff = (2**attempt) + random.uniform(0.5, 1.5)
				time.sleep(backoff)
				self._auth.force_refresh(cdp_url=self._cdp_url)
				self._client = None
				continue

			if code == self._CODE_RATE_LIMITED and attempt < _MAX_RETRIES:
				cooldown = min(60, 10 * (2**attempt))
				time.sleep(cooldown)
				continue

			if self._ADD_ENDPOINT_HINT:
				data.setdefault("__cli_endpoint_hint__", url)
			return data

		raise self._AUTH_ERROR_CLS("请求失败，已达最大重试次数")

	def close(self) -> None:
		"""Release httpx client and browser session. Idempotent."""
		if self._closed:
			return
		self._closed = True
		if self._browser_session:
			self._browser_session.close()
			self._browser_session = None
		if self._client:
			self._client.close()
			self._client = None
		self._unregister()

	def __enter__(self: _SelfT) -> _SelfT:
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_val: BaseException | None,
		exc_tb: TracebackType | None,
	) -> None:
		self.close()
