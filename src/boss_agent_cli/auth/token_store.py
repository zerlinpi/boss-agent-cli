import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from base64 import urlsafe_b64encode
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, cast

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_LOCK_TIMEOUT = 30
_STALE_LOCK_SECONDS = 300


class RefreshLockBusy(RuntimeError):
	"""Raised when another live process still owns the token refresh lock."""


def _chmod_private(path: Path) -> None:
	try:
		path.chmod(0o600)
	except OSError:
		pass


def _atomic_write_private(path: Path, data: bytes) -> None:
	"""Atomically replace sensitive bytes with owner-only permissions where supported."""
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


class TokenStore:
	def __init__(self, auth_dir: Path):
		self._auth_dir = auth_dir
		self._auth_dir.mkdir(parents=True, exist_ok=True)
		self._session_path = auth_dir / "session.enc"
		self._salt_path = auth_dir / "salt"
		self._lock_path = auth_dir / "refresh.lock"

	def _get_machine_id(self) -> str:
		# 允许显式覆盖，便于测试 / CI / 沙箱环境稳定运行
		if override := os.getenv("BOSS_AGENT_MACHINE_ID"):
			return override

		system = platform.system()
		try:
			if system == "Darwin":
				if shutil.which("ioreg"):
					result = subprocess.run(
						["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
						capture_output=True,
						text=True,
						check=False,
					)
					for line in result.stdout.splitlines():
						if "IOPlatformUUID" in line:
							return line.split('"')[-2]
			elif system == "Linux":
				machine_id = Path("/etc/machine-id")
				if machine_id.exists():
					value = machine_id.read_text().strip()
					if value:
						return value
			elif system == "Windows":
				if shutil.which("reg"):
					result = subprocess.run(
						["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
						capture_output=True,
						text=True,
						check=False,
					)
					for line in result.stdout.splitlines():
						if "MachineGuid" in line:
							return line.split()[-1]
		except (OSError, ValueError):
			pass

		# 最终兜底：基于主机名+系统信息稳定生成一个本地 fallback id
		fingerprint = "|".join([
			platform.node() or "unknown-node",
			system or "unknown-system",
			platform.machine() or "unknown-machine",
		])
		return hashlib.sha256(fingerprint.encode()).hexdigest()

	def _get_salt(self) -> bytes:
		if self._salt_path.exists():
			salt = self._salt_path.read_bytes()
			if len(salt) >= 16:
				_chmod_private(self._salt_path)
				return salt
			# A truncated salt cannot decrypt the old session. Remove both sides of the broken pair
			# instead of deriving a new key from corrupt bytes and failing unpredictably later.
			self._session_path.unlink(missing_ok=True)
			self._salt_path.unlink(missing_ok=True)

		salt = os.urandom(16)
		try:
			fd = os.open(self._salt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		except FileExistsError:
			return self._get_salt()
		with os.fdopen(fd, "wb") as handle:
			handle.write(salt)
			handle.flush()
			os.fsync(handle.fileno())
		_chmod_private(self._salt_path)
		return salt

	def _derive_key(self) -> bytes:
		salt = self._get_salt()
		machine_id = self._get_machine_id()
		kdf = PBKDF2HMAC(
			algorithm=hashes.SHA256(),
			length=32,
			salt=salt,
			iterations=480000,
		)
		key = kdf.derive(machine_id.encode())
		return urlsafe_b64encode(key)

	def save(self, token_data: dict[str, Any]) -> None:
		fernet = Fernet(self._derive_key())
		plaintext = json.dumps(token_data, ensure_ascii=False).encode()
		encrypted = fernet.encrypt(plaintext)
		_atomic_write_private(self._session_path, encrypted)

	def load(self) -> dict[str, Any] | None:
		if not self._session_path.exists():
			return None
		try:
			fernet = Fernet(self._derive_key())
			encrypted = self._session_path.read_bytes()
			plaintext = fernet.decrypt(encrypted)
			decoded = json.loads(plaintext)
		except (InvalidToken, ValueError, TypeError, json.JSONDecodeError, OSError, UnicodeDecodeError):
			return None
		if not isinstance(decoded, dict):
			return None
		_chmod_private(self._session_path)
		return cast("dict[str, Any]", decoded)

	def clear(self) -> None:
		"""删除 session.enc 文件（保留 salt 供下次登录复用）"""
		self._session_path.unlink(missing_ok=True)

	def _refresh_lock_is_stale(self) -> bool:
		try:
			age = time.time() - self._lock_path.stat().st_mtime
		except FileNotFoundError:
			return True
		except OSError:
			return False
		return age >= _STALE_LOCK_SECONDS

	@contextmanager
	def refresh_lock(self) -> Iterator[None]:
		"""Acquire refresh lock without stealing it from a still-running refresh operation."""
		deadline = time.monotonic() + _LOCK_TIMEOUT
		fd = None
		while True:
			try:
				fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
				break
			except FileExistsError:
				if time.monotonic() >= deadline:
					if self._refresh_lock_is_stale():
						self._lock_path.unlink(missing_ok=True)
						deadline = time.monotonic() + _LOCK_TIMEOUT
						continue
					raise RefreshLockBusy("已有登录态刷新任务正在运行，请稍后重试")
				time.sleep(0.5)
		try:
			if fd is not None:
				os.close(fd)
			yield
		finally:
			self._lock_path.unlink(missing_ok=True)
