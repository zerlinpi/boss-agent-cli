"""AI service client for OpenAI-compatible APIs.

Provides a simple interface for chat completions with deterministic input and
response validation at the network boundary.
"""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urlparse

import httpx


class AIServiceError(Exception):
	"""Raised when an AI service call fails."""

	def __init__(self, message: str, *, status_code: int | None = None):
		super().__init__(message)
		self.status_code = status_code


def _validated_base_url(value: str) -> str:
	url = str(value or "").strip().rstrip("/")
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
	for index, message in enumerate(messages):
		if not isinstance(message, dict):
			raise AIServiceError(f"messages[{index}] 必须是对象")
		role = message.get("role")
		content = message.get("content")
		if not isinstance(role, str) or not role.strip():
			raise AIServiceError(f"messages[{index}].role 必须是非空字符串")
		if not isinstance(content, str):
			raise AIServiceError(f"messages[{index}].content 必须是字符串")
	return messages


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
		if not self.model:
			raise AIServiceError("模型名称不能为空")
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

		Raises:
			AIServiceError: On invalid input, HTTP/network errors, or unexpected response format.
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

		try:
			response = httpx.post(url, json=payload, headers=headers, timeout=60)
			response.raise_for_status()
		except httpx.HTTPStatusError as exc:
			raise AIServiceError(
				f"API 请求失败: HTTP {exc.response.status_code}",
				status_code=exc.response.status_code,
			) from exc
		except httpx.RequestError as exc:
			raise AIServiceError(f"网络请求失败: {exc}") from exc

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
