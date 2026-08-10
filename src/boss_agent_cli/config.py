import json
import math
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Iterator

_CONFIG_LOCK_TIMEOUT = 5.0
_CONFIG_STALE_LOCK_SECONDS = 60.0
_LOG_LEVELS = {"debug", "info", "warning", "error"}
_ROLES = {"candidate", "recruiter"}

DEFAULTS: dict[str, Any] = {
	"request_delay": [1.5, 3.0],
	"batch_greet_delay": [2.0, 5.0],
	"log_level": "error",
	"cdp_url": None,
	"export_dir": None,
	"platform": "zhipin",
	"role": "candidate",
	"operating_mode": "assisted",
	"low_risk_mode": True,
	"automation": {
		"mode": "autonomous",
		"platforms": ["zhilian", "zhipin"],
		"allowed_actions": [
			"scan_conversations",
			"read_candidate_profile",
			"send_questionnaire",
			"send_follow_up",
			"exchange_contact",
			"create_interview_lead",
		],
		"human_review_threshold": 0.65,
		"auto_execute_threshold": 0.82,
	},
	"crawl": {
		"chrome_path": None,
		"cdp_port": None,
		"hook_profile": "none",
		"hook_dir": None,
		"max_requests": 20,
		"max_details": 50,
		"max_seconds": 600,
		"max_retries": 1,
	},
}


class ConfigLockBusy(RuntimeError):
	"""Raised when another process is still updating the shared config file."""


def _merge_config(defaults: dict[str, Any], user_cfg: dict[str, Any]) -> dict[str, Any]:
	"""Merge top-level user settings while retaining missing nested default fields."""
	cfg = deepcopy(defaults)
	for key, value in user_cfg.items():
		current = cfg.get(key)
		if isinstance(current, dict) and isinstance(value, dict):
			merged = deepcopy(current)
			merged.update(deepcopy(value))
			cfg[key] = merged
		else:
			cfg[key] = deepcopy(value)
	return cfg


def _normalize_delay(value: Any, default: list[float]) -> list[float]:
	if not isinstance(value, (list, tuple)) or len(value) != 2:
		return deepcopy(default)
	clean: list[float] = []
	for item in value:
		if isinstance(item, bool) or not isinstance(item, (int, float)):
			return deepcopy(default)
		number = float(item)
		if not math.isfinite(number) or number < 0:
			return deepcopy(default)
		clean.append(number)
	if clean[0] > clean[1]:
		return deepcopy(default)
	return clean


def _normalize_runtime_config(cfg: dict[str, Any]) -> dict[str, Any]:
	"""Keep malformed hand-edited values from reaching runtime code with incompatible types."""
	cfg["request_delay"] = _normalize_delay(cfg.get("request_delay"), DEFAULTS["request_delay"])
	cfg["batch_greet_delay"] = _normalize_delay(cfg.get("batch_greet_delay"), DEFAULTS["batch_greet_delay"])
	if cfg.get("log_level") not in _LOG_LEVELS:
		cfg["log_level"] = DEFAULTS["log_level"]
	for key in ("cdp_url", "export_dir"):
		value = cfg.get(key)
		if value is not None and not isinstance(value, str):
			cfg[key] = DEFAULTS[key]
	platform_value = cfg.get("platform")
	if not isinstance(platform_value, str) or not platform_value.strip():
		cfg["platform"] = DEFAULTS["platform"]
	if cfg.get("role") not in _ROLES:
		cfg["role"] = DEFAULTS["role"]
	for key in ("automation", "crawl"):
		if not isinstance(cfg.get(key), dict):
			cfg[key] = deepcopy(DEFAULTS[key])
	return cfg


def read_user_config(config_path: Path | None) -> dict[str, Any]:
	"""Read only user overrides; malformed/non-object files safely behave as no overrides."""
	if not config_path or not config_path.exists():
		return {}
	try:
		with open(config_path, encoding="utf-8") as handle:
			loaded = json.load(handle)
	except (OSError, json.JSONDecodeError, UnicodeDecodeError):
		return {}
	return deepcopy(loaded) if isinstance(loaded, dict) else {}


def _atomic_write_config(config_path: Path, payload: dict[str, Any]) -> None:
	config_path.parent.mkdir(parents=True, exist_ok=True)
	data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
	temporary = config_path.with_name(f".{config_path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
	fd: int | None = None
	try:
		fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, "wb") as handle:
			fd = None
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, config_path)
		try:
			config_path.chmod(0o600)
		except OSError:
			pass
	finally:
		if fd is not None:
			os.close(fd)
		try:
			temporary.unlink()
		except FileNotFoundError:
			pass


def _config_lock_is_stale(lock_path: Path) -> bool:
	try:
		return time.time() - lock_path.stat().st_mtime >= _CONFIG_STALE_LOCK_SECONDS
	except FileNotFoundError:
		return True
	except OSError:
		return False


@contextmanager
def config_write_lock(config_path: Path) -> Iterator[None]:
	"""Cross-process lock for read-modify-write config operations."""
	config_path.parent.mkdir(parents=True, exist_ok=True)
	lock_path = config_path.with_name(f"{config_path.name}.lock")
	deadline = time.monotonic() + _CONFIG_LOCK_TIMEOUT
	fd: int | None = None
	while True:
		try:
			fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
			break
		except FileExistsError:
			if time.monotonic() >= deadline:
				if _config_lock_is_stale(lock_path):
					lock_path.unlink(missing_ok=True)
					deadline = time.monotonic() + _CONFIG_LOCK_TIMEOUT
					continue
				raise ConfigLockBusy("配置文件正在被另一个进程修改，请稍后重试")
			time.sleep(0.05)
	try:
		if fd is not None:
			os.close(fd)
			fd = None
		yield
	finally:
		if fd is not None:
			os.close(fd)
		lock_path.unlink(missing_ok=True)


def update_user_config(
	config_path: Path,
	*,
	updates: dict[str, Any] | None = None,
	removals: Iterable[str] = (),
) -> dict[str, Any]:
	"""Atomically merge/remove user overrides without losing concurrent changes to other keys."""
	with config_write_lock(config_path):
		user_cfg = read_user_config(config_path)
		for key in removals:
			user_cfg.pop(str(key), None)
		if updates:
			for key, value in updates.items():
				user_cfg[str(key)] = deepcopy(value)
		_atomic_write_config(config_path, user_cfg)
		return deepcopy(user_cfg)


def replace_user_config(config_path: Path, payload: dict[str, Any]) -> None:
	"""Atomically replace user overrides. Prefer update_user_config for read-modify-write paths."""
	with config_write_lock(config_path):
		_atomic_write_config(config_path, deepcopy(payload))


def load_config(config_path: Path | None) -> dict[str, Any]:
	user_cfg = read_user_config(config_path)
	cfg = _normalize_runtime_config(_merge_config(DEFAULTS, user_cfg))
	mode = user_cfg.get("operating_mode")
	if mode not in {"assisted", "research"}:
		if "low_risk_mode" in user_cfg:
			mode = "research" if user_cfg["low_risk_mode"] is False else "assisted"
		else:
			mode = DEFAULTS.get("operating_mode", "assisted")
	if mode not in {"assisted", "research"}:
		mode = "assisted"
	cfg["operating_mode"] = mode
	cfg["low_risk_mode"] = mode != "research"
	return cfg
