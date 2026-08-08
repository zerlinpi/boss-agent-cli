"""Small file-aware cache for repeatedly read recruiter job profiles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

_INSTALLED = False
_CACHE_ATTR = "_boss_job_profile_cache"


def _mtime_ns(path: Any) -> int | None:
	try:
		return int(path.stat().st_mtime_ns)
	except OSError:
		return None


def install_job_profile_cache(store_cls: type[Any]) -> None:
	"""Reuse parsed job JSON while invalidating on atomic file replacement or deletion."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	original_get_job: Callable[[Any, str], dict[str, Any]] = store_cls.get_job
	original_save_job: Callable[..., dict[str, Any]] = store_cls.save_job

	def cache(self: Any) -> dict[str, dict[str, Any]]:
		value = getattr(self, _CACHE_ATTR, None)
		if not isinstance(value, dict):
			value = {}
			setattr(self, _CACHE_ATTR, value)
		return value

	def get_job(self: Any, job_key: str) -> dict[str, Any]:
		entries = cache(self)
		entry = entries.get(job_key)
		if isinstance(entry, dict):
			path = self.jobs_dir / f"{job_key}.json"
			mtime = _mtime_ns(path)
			if mtime is not None and mtime == entry.get("mtime") and isinstance(entry.get("record"), dict):
				return deepcopy(entry["record"])
			entries.pop(job_key, None)

		record = original_get_job(self, job_key)
		path = self.jobs_dir / f"{job_key}.json"
		mtime = _mtime_ns(path)
		if mtime is not None:
			entries[job_key] = {"mtime": mtime, "record": deepcopy(record)}
		return record

	def save_job(self: Any, **kwargs: Any) -> dict[str, Any]:
		record = original_save_job(self, **kwargs)
		job_key = str(record.get("job_key") or kwargs.get("job_key") or "")
		if job_key:
			path = self.jobs_dir / f"{job_key}.json"
			mtime = _mtime_ns(path)
			if mtime is not None:
				cache(self)[job_key] = {"mtime": mtime, "record": deepcopy(record)}
		return record

	setattr(store_cls, "get_job", get_job)
	setattr(store_cls, "save_job", save_job)
