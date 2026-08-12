"""AI service client for OpenAI-compatible APIs.

Provides a simple interface for chat completions with deterministic input and
response validation at the network boundary.
"""

from __future__ import annotations

import atexit
import math
import time
from threading import Lock
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_MAX_RETRY_DELAY_SECONDS = 5.0
_MAX_BASE_URL_CHARS = 2_048
_MAX_API_KEY_CHARS = 8_192
_MAX_MODEL_CHARS = 256
_MAX_MESSAGES = 100
_MAX_MESSAGE_CHARS = 500_000
_MAX_TOTAL_MESSAGE_CHARS = 1_000_000
_ORIGINAL_HTTPX_POST = httpx.post
_SHARED_CLIENT: httpx.Client | None = None
_SHARED_CLIENT_LOCK = Lock()


class ChatService(Protocol):
	"""Structural contract required by recruiter AI evaluation and drafting helpers."""

	def chat(
		self,
		messages: list[dict[str, Any]],
		*,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> str: ...


class AIServiceError(Exception):
	"""Raised when an AI service call fails."""

	def __init__(self, message: str, *, status_code: int | None = None):
		super().__init__(message)
		self.status_code = status_code


def _shared_client() -> httpx.Client:
	"""Return one thread-safe process client so repeated AI calls reuse pooled connections."""
	global _SHARED_CLIENT
	client = _SHARED_CLIENT
	if client is not None:
		return client
	with _SHARED_CLIENT_LOCK:
		client = _SHARED_CLIENT
		if client is None:
			client = httpx.Client()
			_SHARED_CLIENT = client
		return client


def _close_shared_client() -> None:
	global _SHARED_CLIENT
	with _SHARED_CLIENT_LOCK:
		client, _SHARED_CLIENT = _SHARED_CLIENT, None
	if client is not None:
		try:
			client.close()
		except Exception:
			pass


atexit.register(_close_shared_client)


def _post(url: str, **kwargs: Any) -> httpx.Response:
	"""Use pooled production I/O while preserving existing monkeypatch/test compatibility."""
	# Existing integrations and tests may monkeypatch the module-level httpx.post function. Honor
	# that hook when present; normal production calls use the shared Client connection pool.
	if httpx.post is not _ORIGINAL_HTTPX_POST:
		return httpx.post(url, **kwargs)
	return _shared_client().post(url, **kwargs)


def _validated_base_url(value: str) -> str:
	url = str(value or "").strip().rstrip("/")
	if len(url) > _MAX_BASE_URL_CHARS:
		raise AIServiceError(f"AI Base URL 过长，最多 {_MAX_BASE_URL_CHARS} 字符")
	parsed = urlparse(url)
	if parsed.scheme not in {"http", "https"} or not parsed.netloc:
		raise AIServiceError("AI Base URL 必须是完整的 HTTP(S) 地址")
	if parsed.username or parsed.password:
		raise AIServiceError("AI Base URL 不应包含用户名或密码")
	return url


def _validated_temperature(value: Any) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise AIServiceError("temperature 必须是 0-2 之间的有限数字")
	number = float(value)
	if not math.isfinite(number) or not 0 <= number <= 2:
		raise AIServiceError("temperature 必须是 0-2 之间的有限数字")
	return number


def _validated_max_tokens(value: Any) -> int:
	if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1_000_000:
		raise AIServiceError("max_tokens 必须是 1-1000000 的整数")
	return value


def _validated_messages(messages: Any) -> list[dict[str, Any]]:
	if not isinstance(messages, list) or not messages:
		raise AIServiceError("messages 必须是非空列表")
	if len(messages) > _MAX_MESSAGES:
		raise AIServiceError(f"messages 最多 {_MAX_MESSAGES} 条")
	total_chars = 0
	for index, message in enumerate(messages):
		if not isinstance(message, dict):
			raise AIServiceError(f"messages[{index}] 必须是对象")
		role = message.get("role")
		content = message.get("content")
		if not isinstance(role, str) or not role.strip():
			raise AIServiceError(f"messages[{index}].role 必须是非空字符串")
		if len(role) > 64:
			raise AIServiceError(f"messages[{index}].role 过长")
		if not isinstance(content, str):
			raise AIServiceError(f"messages[{index}].content 必须是字符串")
		if len(content) > _MAX_MESSAGE_CHARS:
			raise AIServiceError(f"messages[{index}].content 超过 {_MAX_MESSAGE_CHARS} 字符限制")
		total_chars += len(content)
		if total_chars > _MAX_TOTAL_MESSAGE_CHARS:
			raise AIServiceError(f"messages 总内容超过 {_MAX_TOTAL_MESSAGE_CHARS} 字符限制")
	return messages


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
	if response is not None:
		retry_after = response.headers.get("Retry-After")
		if retry_after:
			try:
				seconds = float(retry_after)
			except ValueError:
				seconds = -1.0
			if math.isfinite(seconds) and 0 <= seconds <= _MAX_RETRY_DELAY_SECONDS:
				return seconds
	backoff = 0.5 * (2.0 ** attempt)
	return min(backoff, 2.0)


class AIService:
	"""Client for OpenAI-compatible chat completion APIs."""

	def __init__(
		self,
		base_url: str,
		api_key: str,
		model: str,
		temperature: float = 0.7,
		max_tokens: int = 4096,
	):
		self.base_url = _validated_base_url(base_url)
		self.api_key = str(api_key or "").strip()
		self.model = str(model or "").strip()
		if not self.api_key:
			raise AIServiceError("API Key 不能为空")
		if len(self.api_key) > _MAX_API_KEY_CHARS:
			raise AIServiceError(f"API Key 过长，最多 {_MAX_API_KEY_CHARS} 字符")
		if not self.model:
			raise AIServiceError("模型名称不能为空")
		if len(self.model) > _MAX_MODEL_CHARS:
			raise AIServiceError(f"模型名称过长，最多 {_MAX_MODEL_CHARS} 字符")
		self.temperature = _validated_temperature(temperature)
		self.max_tokens = _validated_max_tokens(max_tokens)

	def chat(
		self,
		messages: list[dict[str, Any]],
		*,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> str:
		"""Send a chat completion request and return the assistant's reply text.

		Only errors that clearly indicate a request was not accepted successfully are retried.
		Read timeouts are not retried automatically because the provider may already have processed
		the request, which could duplicate billable model work.
		"""
		safe_messages = _validated_messages(messages)
		effective_temperature = self.temperature if temperature is None else _validated_temperature(temperature)
		effective_max_tokens = self.max_tokens if max_tokens is None else _validated_max_tokens(max_tokens)
		url = f"{self.base_url}/chat/completions"
		headers = {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json",
		}
		payload = {
			"model": self.model,
			"messages": safe_messages,
			"temperature": effective_temperature,
			"max_tokens": effective_max_tokens,
		}

		response: httpx.Response | None = None
		for attempt in range(_MAX_ATTEMPTS):
			try:
				response = _post(url, json=payload, headers=headers, timeout=60)
				response.raise_for_status()
				break
			except httpx.HTTPStatusError as exc:
				status_code = exc.response.status_code
				if status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_ATTEMPTS - 1:
					time.sleep(_retry_delay(exc.response, attempt))
					continue
				raise AIServiceError(
					f"API 请求失败: HTTP {status_code}",
					status_code=status_code,
				) from exc
			except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
				if attempt < _MAX_ATTEMPTS - 1:
					time.sleep(_retry_delay(None, attempt))
					continue
				raise AIServiceError(f"网络请求失败: {exc}") from exc
			except httpx.RequestError as exc:
				raise AIServiceError(f"网络请求失败: {exc}") from exc
		if response is None:
			raise AIServiceError("AI 服务未返回响应")

		try:
			data = response.json()
		except (ValueError, TypeError) as exc:
			raise AIServiceError("响应格式异常: 返回内容不是有效 JSON") from exc
		try:
			content = data["choices"][0]["message"]["content"]
		except (KeyError, IndexError, TypeError) as exc:
			raise AIServiceError(f"响应格式异常: {exc}") from exc
		if not isinstance(content, str):
			raise AIServiceError("响应格式异常: message.content 必须是字符串")
		return content
