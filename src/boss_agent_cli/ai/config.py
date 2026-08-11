"""AI service configuration management.

Handles API key encryption (Fernet), provider settings, and model configuration.
Reuses the auth salt file for key derivation.
"""

import hashlib
import json
import math
import os
import platform
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from boss_agent_cli.auth.token_store import TokenStore

PROVIDER_BASE_URLS: dict[str, str | None] = {
	"openai": "https://api.openai.com/v1",
	"deepseek": "https://api.deepseek.com/v1",
	"moonshot": "https://api.moonshot.cn/v1",
	"openrouter": "https://openrouter.ai/api/v1",
	"qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
	"zhipu": "https://open.bigmodel.cn/api/paas/v4",
	"siliconflow": "https://api.siliconflow.cn/v1",
	"atlas": "https://api.atlascloud.ai/v1",
	"ollama": "http://localhost:11434/v1",
	"vllm": "http://localhost:8000/v1",
	"custom": None,
}
_LOCAL_PROVIDER_PORTS = {"ollama": 11434, "vllm": 8000}
_LOOPBACK_AI_HOSTS = {"localhost", "127.0.0.1", "::1"}
_MAX_API_KEY_CHARS = 8192
_MAX_MODEL_CHARS = 256
_MAX_BASE_URL_CHARS = 2048

_DEFAULT_CONFIG: dict[str, Any] = {
	"ai_provider": None,
	"ai_model": None,
	"ai_base_url": None,
	"ai_temperature": 0.7,
	"ai_max_tokens": 4096,
}
_CONFIG_KEYS = frozenset(_DEFAULT_CONFIG)


def _chmod_private(path: Path) -> None:
	try:
		path.chmod(0o600)
	except OSError:
		pass


def _atomic_write(path: Path, data: bytes) -> None:
	temporary = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
	fd: int | None = None
	try:
		fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, "wb") as handle:
			fd = None
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, path)
		_chmod_private(path)
	finally:
		if fd is not None:
			os.close(fd)
		try:
			temporary.unlink()
		except FileNotFoundError:
			pass


def _validate_base_url(value: Any) -> str | None:
	if value is None:
		return None
	if not isinstance(value, str):
		raise ValueError("ai_base_url 必须是字符串或 null")
	url = value.strip().rstrip("/")
	if not url:
		return None
	if len(url) > _MAX_BASE_URL_CHARS:
		raise ValueError(f"ai_base_url 过长，最多 {_MAX_BASE_URL_CHARS} 字符")
	try:
		parsed = urlparse(url)
	except ValueError as exc:
		raise ValueError("ai_base_url 必须是完整的 HTTP(S) 地址") from exc
	if parsed.scheme not in {"http", "https"} or not parsed.netloc:
		raise ValueError("ai_base_url 必须是完整的 HTTP(S) 地址")
	if parsed.username or parsed.password:
		raise ValueError("ai_base_url 不应包含用户名或密码")
	try:
		_ = parsed.port
	except ValueError as exc:
		raise ValueError("ai_base_url 端口无效") from exc
	return url


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
	validated = dict(config)
	provider = validated.get("ai_provider")
	if provider is not None:
		if not isinstance(provider, str) or provider not in PROVIDER_BASE_URLS:
			raise ValueError(f"不支持的 AI provider: {provider!r}")
	model = validated.get("ai_model")
	if model is not None:
		if not isinstance(model, str) or not model.strip():
			raise ValueError("ai_model 必须是非空字符串")
		model = model.strip()
		if len(model) > _MAX_MODEL_CHARS:
			raise ValueError(f"ai_model 过长，最多 {_MAX_MODEL_CHARS} 字符")
		validated["ai_model"] = model
	validated["ai_base_url"] = _validate_base_url(validated.get("ai_base_url"))

	temperature = validated.get("ai_temperature", 0.7)
	if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
		raise ValueError("ai_temperature 必须是 0-2 的有限数字")
	temperature = float(temperature)
	if not math.isfinite(temperature) or not 0 <= temperature <= 2:
		raise ValueError("ai_temperature 必须是 0-2 的有限数字")
	validated["ai_temperature"] = temperature

	max_tokens = validated.get("ai_max_tokens", 4096)
	if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 1_000_000:
		raise ValueError("ai_max_tokens 必须是 1-1000000 的整数")
	return validated


def _docker_local_ai_url(provider: str, configured_url: str | None) -> str | None:
	local_host = os.getenv("BOSS_LOCAL_AI_HOST", "").strip()
	if not local_host or "://" in local_host or "/" in local_host or ":" in local_host:
		return None
	port = _LOCAL_PROVIDER_PORTS[provider]
	path = "/v1"
	scheme = "http"
	if configured_url:
		try:
			parsed = urlparse(configured_url)
		except ValueError:
			return None
		if parsed.hostname not in _LOOPBACK_AI_HOSTS:
			return None
		scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "http"
		try:
			port = parsed.port or port
		except ValueError:
			return None
		path = parsed.path.rstrip("/") or "/v1"
	return f"{scheme}://{local_host}:{port}{path}"


class AIConfigStore:
	"""Manages AI service configuration with encrypted API key storage."""

	def __init__(self, data_dir: Path):
		self._data_dir = data_dir
		self._ai_dir = data_dir / "ai"
		self._ai_dir.mkdir(parents=True, exist_ok=True)
		self._key_path = self._ai_dir / "api_key.enc"
		self._config_path = self._ai_dir / "config.json"
		self._auth_dir = data_dir / "auth"
		self._derived_key_cache: bytes | None = None

	def _legacy_machine_id(self) -> str:
		fingerprint = "|".join([
			platform.node() or "unknown-node",
			platform.system() or "unknown-system",
			platform.machine() or "unknown-machine",
		])
		return hashlib.sha256(fingerprint.encode()).hexdigest()

	def _get_machine_id(self) -> str:
		return TokenStore(self._auth_dir)._get_machine_id()

	def _get_salt(self) -> bytes:
		self._auth_dir.mkdir(parents=True, exist_ok=True)
		salt_path = self._auth_dir / "salt"
		if salt_path.exists():
			try:
				salt = salt_path.read_bytes()
			except OSError:
				salt = b""
			if len(salt) >= 16:
				_chmod_private(salt_path)
				return salt
			try:
				self._key_path.unlink()
			except FileNotFoundError:
				pass
			salt = os.urandom(16)
			_atomic_write(salt_path, salt)
			self._derived_key_cache = None
			return salt

		salt = os.urandom(16)
		try:
			fd = os.open(salt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		except FileExistsError:
			return self._get_salt()
		with os.fdopen(fd, "wb") as handle:
			handle.write(salt)
			handle.flush()
			os.fsync(handle.fileno())
		_chmod_private(salt_path)
		return salt

	def _derive_key_for_machine_id(self, machine_id: str) -> bytes:
		kdf = PBKDF2HMAC(
			algorithm=hashes.SHA256(),
			length=32,
			salt=self._get_salt(),
			iterations=480000,
		)
		return urlsafe_b64encode(kdf.derive(machine_id.encode()))

	def _derive_key(self) -> bytes:
		if self._derived_key_cache is not None:
			return self._derived_key_cache
		self._derived_key_cache = self._derive_key_for_machine_id(self._get_machine_id())
		return self._derived_key_cache

	def save_api_key(self, key: str) -> None:
		if not isinstance(key, str) or not key.strip():
			raise ValueError("API Key 不能为空")
		if len(key) > _MAX_API_KEY_CHARS:
			raise ValueError(f"API Key 过长，最多 {_MAX_API_KEY_CHARS} 字符")
		fernet = Fernet(self._derive_key())
		encrypted = fernet.encrypt(key.encode("utf-8"))
		_atomic_write(self._key_path, encrypted)

	def get_api_key(self) -> str | None:
		if not self._key_path.exists():
			return None
		try:
			encrypted = self._key_path.read_bytes()
		except OSError:
			return None
		try:
			plaintext = Fernet(self._derive_key()).decrypt(encrypted)
			return plaintext.decode("utf-8")
		except (InvalidToken, ValueError, UnicodeDecodeError):
			pass

		current_machine_id = self._get_machine_id()
		legacy_machine_id = self._legacy_machine_id()
		if legacy_machine_id == current_machine_id:
			return None
		try:
			legacy_key = self._derive_key_for_machine_id(legacy_machine_id)
			plaintext = Fernet(legacy_key).decrypt(encrypted)
			decoded = plaintext.decode("utf-8")
		except (InvalidToken, ValueError, UnicodeDecodeError):
			return None
		try:
			self.save_api_key(decoded)
		except OSError:
			pass
		return decoded

	def save_config(self, **kwargs: Any) -> None:
		unknown = set(kwargs) - _CONFIG_KEYS
		if unknown:
			raise ValueError(f"unknown AI config fields: {', '.join(sorted(unknown))}")
		current = self.load_config()
		current.update(kwargs)
		validated = _validate_config(current)
		_atomic_write(
			self._config_path,
			json.dumps(validated, ensure_ascii=False, indent=2).encode("utf-8"),
		)

	def load_config(self) -> dict[str, Any]:
		config = dict(_DEFAULT_CONFIG)
		if self._config_path.exists():
			try:
				saved = json.loads(self._config_path.read_text(encoding="utf-8"))
			except (json.JSONDecodeError, OSError, UnicodeDecodeError):
				saved = None
			if isinstance(saved, dict):
				config.update({key: value for key, value in saved.items() if key in _CONFIG_KEYS})
				_chmod_private(self._config_path)
		return config

	def get_base_url(self) -> str | None:
		config = self.load_config()
		provider = config.get("ai_provider")
		raw_base_url = config.get("ai_base_url")
		base_url = raw_base_url.strip() if isinstance(raw_base_url, str) else ""
		if isinstance(provider, str) and provider in _LOCAL_PROVIDER_PORTS:
			docker_url = _docker_local_ai_url(provider, base_url or None)
			if docker_url:
				return docker_url
		if base_url:
			return base_url
		if isinstance(provider, str) and provider in PROVIDER_BASE_URLS:
			return PROVIDER_BASE_URLS[provider]
		return None

	def is_configured(self) -> bool:
		config = self.load_config()
		provider = config.get("ai_provider")
		model = config.get("ai_model")
		api_key = self.get_api_key()
		return all([provider, model, api_key])
