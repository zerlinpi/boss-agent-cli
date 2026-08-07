"""AI service configuration management.

Handles API key encryption (Fernet), provider settings, and model configuration.
Reuses the auth salt file for key derivation.
"""

import hashlib
import json
import os
import platform
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

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

_DEFAULT_CONFIG: dict[str, Any] = {
	"ai_provider": None,
	"ai_model": None,
	"ai_base_url": None,
	"ai_temperature": 0.7,
	"ai_max_tokens": 4096,
}
_CONFIG_KEYS = frozenset(_DEFAULT_CONFIG)


def _chmod_private(path: Path) -> None:
	"""Best-effort owner-only permissions on POSIX; harmless on platforms without full chmod semantics."""
	try:
		path.chmod(0o600)
	except OSError:
		pass


def _atomic_write(path: Path, data: bytes) -> None:
	"""Replace a sensitive config file atomically and apply owner-only permissions."""
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

	def _get_machine_id(self) -> str:
		"""Get a stable machine identifier for key derivation."""
		if override := os.getenv("BOSS_AGENT_MACHINE_ID"):
			return override
		fingerprint = "|".join([
			platform.node() or "unknown-node",
			platform.system() or "unknown-system",
			platform.machine() or "unknown-machine",
		])
		return hashlib.sha256(fingerprint.encode()).hexdigest()

	def _get_salt(self) -> bytes:
		"""Reuse auth salt file, or create one with owner-only permissions."""
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
			# A corrupt/empty salt cannot decrypt the old key anyway. Reset both consistently.
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

	def _derive_key(self) -> bytes:
		"""Derive and cache a Fernet key from machine ID and salt."""
		if self._derived_key_cache is not None:
			return self._derived_key_cache
		salt = self._get_salt()
		machine_id = self._get_machine_id()
		kdf = PBKDF2HMAC(
			algorithm=hashes.SHA256(),
			length=32,
			salt=salt,
			iterations=480000,
		)
		key = urlsafe_b64encode(kdf.derive(machine_id.encode()))
		self._derived_key_cache = key
		return key

	def save_api_key(self, key: str) -> None:
		"""Encrypt and persist the API key atomically."""
		fernet = Fernet(self._derive_key())
		encrypted = fernet.encrypt(key.encode("utf-8"))
		_atomic_write(self._key_path, encrypted)

	def get_api_key(self) -> str | None:
		"""Load and decrypt the API key. Returns None if not set, unreadable, or invalid."""
		if not self._key_path.exists():
			return None
		try:
			fernet = Fernet(self._derive_key())
			plaintext = fernet.decrypt(self._key_path.read_bytes())
			return plaintext.decode("utf-8")
		except (InvalidToken, ValueError, OSError, UnicodeDecodeError):
			return None

	def save_config(self, **kwargs: Any) -> None:
		"""Save known configuration fields, merging with existing values."""
		unknown = set(kwargs) - _CONFIG_KEYS
		if unknown:
			raise ValueError(f"unknown AI config fields: {', '.join(sorted(unknown))}")
		current = self.load_config()
		current.update(kwargs)
		_atomic_write(
			self._config_path,
			json.dumps(current, ensure_ascii=False, indent=2).encode("utf-8"),
		)

	def load_config(self) -> dict[str, Any]:
		"""Load configuration with defaults for missing or malformed content."""
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
		"""Get the API base URL: user config takes priority, then provider lookup."""
		config = self.load_config()
		base_url = config.get("ai_base_url")
		if base_url:
			return str(base_url)
		provider = config.get("ai_provider")
		if provider and provider in PROVIDER_BASE_URLS:
			return PROVIDER_BASE_URLS[provider]
		return None

	def is_configured(self) -> bool:
		"""Check if all required settings are present (provider + model + api_key)."""
		config = self.load_config()
		provider = config.get("ai_provider")
		model = config.get("ai_model")
		api_key = self.get_api_key()
		return all([provider, model, api_key])
