"""搜索结果索引缓存，支持 boss show N 快速导航。
缓存文件: ~/.boss-agent/cache/index_cache.json
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from boss_agent_cli.output import Logger

_CACHE_FILE = "index_cache.json"


def _cache_path(data_dir: Path) -> Path:
	return data_dir / "cache" / _CACHE_FILE


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
	"""Atomically replace the rebuildable cache and keep it private on POSIX."""
	path.parent.mkdir(parents=True, exist_ok=True)
	temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
	data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
	fd: int | None = None
	try:
		fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, "wb") as handle:
			fd = None
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, path)
		try:
			path.chmod(0o600)
		except OSError:
			pass
	finally:
		if fd is not None:
			os.close(fd)
		try:
			temporary.unlink(missing_ok=True)
		except OSError:
			pass


def save_index(data_dir: Path, jobs: list[dict[str, Any]], source: str = "search") -> None:
	"""保存搜索/推荐结果到索引缓存。"""
	entries: list[dict[str, Any]] = []
	for job in jobs:
		entries.append({
			"security_id": job.get("security_id", ""),
			"job_id": job.get("job_id", ""),
			"title": job.get("title", ""),
			"company": job.get("company", ""),
			"salary": job.get("salary", ""),
			"city": job.get("city", ""),
			"experience": job.get("experience", ""),
			"education": job.get("education", ""),
			"skills": job.get("skills", []),
			"raw_job_type": job.get("raw_job_type"),
			"employment_type": job.get("employment_type", ""),
			"days_per_week": job.get("days_per_week", ""),
			"least_month": job.get("least_month", ""),
		})

	cache_data = {
		"source": str(source),
		"count": len(entries),
		"saved_at": time.time(),
		"jobs": entries,
	}
	_atomic_write(_cache_path(data_dir), cache_data)


def try_save_index(data_dir: Path, jobs: list[dict[str, Any]], *, source: str = "search", logger: Logger | None = None) -> bool:
	"""Best-effort 保存索引缓存，失败时记录 warning，不影响主命令成功返回。"""
	try:
		save_index(data_dir, jobs, source=source)
		return True
	except OSError as exc:
		if logger:
			logger.warning(f"索引缓存写入失败，已跳过: {exc}")
		return False


def _load_cache(data_dir: Path) -> dict[str, Any] | None:
	"""读取索引缓存；缺文件、解析失败或结构损坏均返回 None。"""
	path = _cache_path(data_dir)
	if not path.is_file():
		return None
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except (json.JSONDecodeError, OSError, UnicodeDecodeError):
		return None
	if not isinstance(payload, dict):
		return None
	jobs = payload.get("jobs")
	if not isinstance(jobs, list) or any(not isinstance(item, dict) for item in jobs):
		return None
	return cast("dict[str, Any]", payload)


def get_job_by_index(data_dir: Path, index: int) -> dict[str, Any] | None:
	"""按 1-based 编号获取缓存的职位信息。"""
	cache_data = _load_cache(data_dir)
	if cache_data is None:
		return None

	jobs = cast("list[dict[str, Any]]", cache_data["jobs"])
	if index < 1 or index > len(jobs):
		return None
	return jobs[index - 1]


def get_index_info(data_dir: Path) -> dict[str, Any]:
	"""获取缓存元信息（来源、数量、保存时间）。"""
	cache_data = _load_cache(data_dir)
	if cache_data is None:
		return {"exists": False, "source": "", "count": 0, "saved_at": 0}

	jobs = cast("list[dict[str, Any]]", cache_data["jobs"])
	return {
		"exists": True,
		"source": str(cache_data.get("source") or ""),
		"count": len(jobs),
		"saved_at": cache_data.get("saved_at", 0),
	}
