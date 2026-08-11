"""Row-level JSON validation for the rebuildable SQLite cache."""

from __future__ import annotations

import json
from typing import Any, cast


class CacheRowCorruptionError(RuntimeError):
	"""Raised when SQLite is healthy but a structured JSON field is corrupt."""


def _decode_object(raw: Any, *, table: str, field: str, identity: str) -> dict[str, Any]:
	try:
		payload = json.loads(raw)
	except (TypeError, json.JSONDecodeError) as exc:
		raise CacheRowCorruptionError(f"缓存行损坏: {table}.{field} ({identity}) 不是有效 JSON") from exc
	if not isinstance(payload, dict):
		raise CacheRowCorruptionError(f"缓存行损坏: {table}.{field} ({identity}) 顶层必须是对象")
	return cast("dict[str, Any]", payload)


def _decode_list(raw: Any, *, table: str, field: str, identity: str) -> list[Any]:
	try:
		payload = json.loads(raw)
	except (TypeError, json.JSONDecodeError) as exc:
		raise CacheRowCorruptionError(f"缓存行损坏: {table}.{field} ({identity}) 不是有效 JSON") from exc
	if not isinstance(payload, list):
		raise CacheRowCorruptionError(f"缓存行损坏: {table}.{field} ({identity}) 顶层必须是数组")
	return payload


def install_cache_row_safety(store_cls: type[Any]) -> None:
	"""Replace structured-row readers with explicit shape validation."""
	if getattr(store_cls, "_boss_cache_row_safety_installed", False):
		return

	def get_crawl_run(self: Any, run_id: str) -> dict[str, Any] | None:
		row = self._conn.execute(
			"SELECT run_id, params, status, stop_requested, requests_attempted, detail_requests_attempted, elapsed_seconds, "
			"next_page, list_finished, output_dir, error, hook_results, created_at, updated_at "
			"FROM crawl_runs WHERE run_id = ?",
			(run_id,),
		).fetchone()
		if row is None:
			return None
		identity = f"run_id={run_id}"
		return {
			"run_id": row[0],
			"params": _decode_object(row[1], table="crawl_runs", field="params", identity=identity),
			"status": row[2],
			"stop_requested": bool(row[3]),
			"requests_attempted": int(row[4]),
			"detail_requests_attempted": int(row[5]),
			"elapsed_seconds": int(row[6]),
			"next_page": row[7],
			"list_finished": bool(row[8]),
			"output_dir": row[9],
			"error": row[10],
			"hook_results": _decode_list(row[11], table="crawl_runs", field="hook_results", identity=identity),
			"created_at": row[12],
			"updated_at": row[13],
		}

	def get_crawl_job(self: Any, run_id: str, job_key: str) -> dict[str, Any] | None:
		row = self._conn.execute(
			"SELECT selector, page_no, payload, detail_done FROM crawl_jobs WHERE run_id = ? AND job_key = ?",
			(run_id, job_key),
		).fetchone()
		if row is None:
			return None
		identity = f"run_id={run_id}, job_key={job_key}"
		return {
			"selector": row[0],
			"page_no": row[1],
			"payload": _decode_object(row[2], table="crawl_jobs", field="payload", identity=identity),
			"detail_done": bool(row[3]),
		}

	def list_crawl_jobs(self: Any, run_id: str) -> list[dict[str, Any]]:
		rows = self._conn.execute(
			"SELECT job_key, selector, page_no, payload, detail_done FROM crawl_jobs WHERE run_id = ? ORDER BY page_no, rowid",
			(run_id,),
		).fetchall()
		items: list[dict[str, Any]] = []
		for row in rows:
			job_key = str(row[0])
			identity = f"run_id={run_id}, job_key={job_key}"
			items.append({
				"job_key": job_key,
				"selector": row[1],
				"page_no": row[2],
				"payload": _decode_object(row[3], table="crawl_jobs", field="payload", identity=identity),
				"detail_done": bool(row[4]),
			})
		return items

	setattr(store_cls, "get_crawl_run", get_crawl_run)
	setattr(store_cls, "get_crawl_job", get_crawl_job)
	setattr(store_cls, "list_crawl_jobs", list_crawl_jobs)
	setattr(store_cls, "_boss_cache_row_safety_installed", True)
