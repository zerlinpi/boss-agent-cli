"""Persistent background tasks for long-running Web console actions."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

TaskFunction = Callable[[Callable[[int, str], None]], dict[str, Any]]


def _now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _scrub_result(value: Any, evaluation_ids: set[str]) -> tuple[Any, bool]:
	"""Remove deleted candidate references from nested persisted task results."""
	if isinstance(value, dict):
		changed = False
		cleaned: dict[str, Any] = {}
		for key, item in value.items():
			if key in {"evaluation_ids", "skipped_ids"} and isinstance(item, list):
				filtered = [entry for entry in item if str(entry) not in evaluation_ids]
				cleaned[key] = filtered
				changed = changed or len(filtered) != len(item)
				continue
			child, child_changed = _scrub_result(item, evaluation_ids)
			cleaned[key] = child
			changed = changed or child_changed
		return cleaned, changed
	if isinstance(value, list):
		changed = False
		cleaned_items: list[Any] = []
		for item in value:
			if isinstance(item, dict) and str(item.get("evaluation_id") or "") in evaluation_ids:
				changed = True
				continue
			child, child_changed = _scrub_result(item, evaluation_ids)
			cleaned_items.append(child)
			changed = changed or child_changed
		return cleaned_items, changed
	return value, False


class TaskManager:
	"""Run Web jobs asynchronously and retain task history across restarts."""

	def __init__(
		self,
		*,
		storage_path: Path | None = None,
		max_workers: int = 2,
		max_tasks: int = 200,
	):
		self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="boss-web")
		self._max_tasks = max_tasks
		self._tasks: dict[str, dict[str, Any]] = {}
		self._lock = Lock()
		self._storage_path = storage_path
		self._db: sqlite3.Connection | None = None
		if storage_path is not None:
			storage_path.parent.mkdir(parents=True, exist_ok=True)
			self._db = sqlite3.connect(storage_path, check_same_thread=False, timeout=5.0)
			self._db.row_factory = sqlite3.Row
			self._initialize_db()
			self._load_from_db()

	def _initialize_db(self) -> None:
		assert self._db is not None
		self._db.execute("PRAGMA journal_mode=WAL")
		self._db.execute("PRAGMA synchronous=NORMAL")
		self._db.execute("PRAGMA busy_timeout=5000")
		self._db.execute(
			"""
			CREATE TABLE IF NOT EXISTS web_tasks (
				id TEXT PRIMARY KEY,
				kind TEXT NOT NULL,
				status TEXT NOT NULL,
				progress INTEGER NOT NULL,
				message TEXT NOT NULL,
				created_at TEXT NOT NULL,
				updated_at TEXT NOT NULL,
				result_json TEXT,
				error_json TEXT,
				metadata_json TEXT
			)
			"""
		)
		self._db.commit()

	def _load_from_db(self) -> None:
		assert self._db is not None
		rows = self._db.execute(
			"SELECT * FROM web_tasks ORDER BY created_at DESC LIMIT ?", (self._max_tasks,)
		).fetchall()
		for row in rows:
			item = self._row_to_task(row)
			if item["status"] in {"queued", "running"}:
				item.update({
					"status": "failed",
					"message": "服务重启，任务已中断",
					"error": {"code": "TASK_INTERRUPTED", "message": "服务重启，任务已中断"},
					"updated_at": _now(),
				})
				self._persist(item)
			self._tasks[str(item["id"])] = item

	@staticmethod
	def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
		def decode(value: str | None) -> Any:
			return json.loads(value) if value else None
		return {
			"id": row["id"],
			"kind": row["kind"],
			"status": row["status"],
			"progress": row["progress"],
			"message": row["message"],
			"created_at": row["created_at"],
			"updated_at": row["updated_at"],
			"result": decode(row["result_json"]),
			"error": decode(row["error_json"]),
			"metadata": decode(row["metadata_json"]) or {},
		}

	def _persist(self, task: dict[str, Any]) -> None:
		if self._db is None:
			return
		try:
			self._db.execute(
				"""
				INSERT INTO web_tasks (
					id, kind, status, progress, message, created_at, updated_at,
					result_json, error_json, metadata_json
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				ON CONFLICT(id) DO UPDATE SET
					status=excluded.status,
					progress=excluded.progress,
					message=excluded.message,
					updated_at=excluded.updated_at,
					result_json=excluded.result_json,
					error_json=excluded.error_json,
					metadata_json=excluded.metadata_json
				""",
				(
					task["id"], task["kind"], task["status"], task["progress"], task["message"],
					task["created_at"], task["updated_at"],
					json.dumps(task.get("result"), ensure_ascii=False) if task.get("result") is not None else None,
					json.dumps(task.get("error"), ensure_ascii=False) if task.get("error") is not None else None,
					json.dumps(task.get("metadata") or {}, ensure_ascii=False),
				),
			)
			self._db.commit()
		except sqlite3.Error:
			return

	def submit(
		self,
		kind: str,
		function: TaskFunction,
		*,
		metadata: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		task_id = f"task_{uuid4().hex[:12]}"
		task = {
			"id": task_id,
			"kind": kind,
			"status": "queued",
			"progress": 0,
			"message": "等待执行",
			"created_at": _now(),
			"updated_at": _now(),
			"result": None,
			"error": None,
			"metadata": metadata or {},
		}
		with self._lock:
			self._tasks[task_id] = task
			self._persist(task)
			self._prune_locked()
		self._executor.submit(self._run, task_id, function)
		return deepcopy(task)

	def _run(self, task_id: str, function: TaskFunction) -> None:
		self._update(task_id, status="running", progress=1, message="正在执行")

		def progress(value: int, message: str) -> None:
			self._update(task_id, progress=max(0, min(int(value), 100)), message=message)

		try:
			result = function(progress)
		except Exception as exc:
			code = getattr(exc, "code", exc.__class__.__name__)
			self._update(
				task_id,
				status="failed",
				message=str(exc),
				error={"code": str(code), "message": str(exc)},
			)
			return
		self._update(
			task_id,
			status="completed",
			progress=100,
			message="执行完成",
			result=result,
		)

	def _update(self, task_id: str, **changes: Any) -> None:
		with self._lock:
			task = self._tasks.get(task_id)
			if task is None:
				return
			task.update(changes)
			task["updated_at"] = _now()
			self._persist(task)

	def get(self, task_id: str) -> dict[str, Any] | None:
		with self._lock:
			task = self._tasks.get(task_id)
			return deepcopy(task) if task else None

	def recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
		with self._lock:
			items = sorted(
				self._tasks.values(),
				key=lambda item: str(item.get("created_at", "")),
				reverse=True,
			)
			return deepcopy(items[: max(1, min(limit, 200))])

	def has_active_screening(self, job_key: str | None = None) -> bool:
		"""Return whether a matching screening task is queued or running."""
		with self._lock:
			for task in self._tasks.values():
				if task.get("status") not in {"queued", "running"}:
					continue
				if task.get("kind") not in {"screen-local", "screen-boss"}:
					continue
				metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
				result = task.get("result") if isinstance(task.get("result"), dict) else {}
				task_job_key = str(metadata.get("job_key") or result.get("job_key") or "")
				if job_key is None or not task_job_key or task_job_key == job_key:
					return True
		return False

	def scrub_evaluations(self, evaluation_ids: list[str]) -> int:
		"""Remove deleted candidate references from all persisted task results."""
		identifiers = {str(item) for item in evaluation_ids if item}
		if not identifiers:
			return 0
		updated = 0
		with self._lock:
			for task in self._tasks.values():
				result = task.get("result")
				if not isinstance(result, (dict, list)):
					continue
				cleaned, changed = _scrub_result(result, identifiers)
				if not changed:
					continue
				task["result"] = cleaned
				task["updated_at"] = _now()
				self._persist(task)
				updated += 1
		return updated

	def delete_for_job(self, job_key: str) -> int:
		"""Delete persisted task records linked to a deleted job."""
		deleted_ids: list[str] = []
		with self._lock:
			for task_id, task in list(self._tasks.items()):
				metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
				result = task.get("result") if isinstance(task.get("result"), dict) else {}
				if str(metadata.get("job_key") or result.get("job_key") or "") != job_key:
					continue
				deleted_ids.append(task_id)
				self._tasks.pop(task_id, None)
			if self._db is not None and deleted_ids:
				try:
					self._db.executemany("DELETE FROM web_tasks WHERE id = ?", [(task_id,) for task_id in deleted_ids])
					self._db.commit()
				except sqlite3.Error:
					pass
		return len(deleted_ids)

	def _prune_locked(self) -> None:
		if len(self._tasks) <= self._max_tasks:
			return
		completed = sorted(
			(item for item in self._tasks.values() if item.get("status") in {"completed", "failed"}),
			key=lambda item: str(item.get("updated_at", "")),
		)
		for item in completed[: max(0, len(self._tasks) - self._max_tasks)]:
			task_id = str(item["id"])
			self._tasks.pop(task_id, None)
			if self._db is not None:
				self._db.execute("DELETE FROM web_tasks WHERE id = ?", (task_id,))
		if self._db is not None:
			self._db.commit()

	def close(self) -> None:
		self._executor.shutdown(wait=False, cancel_futures=True)
		if self._db is not None:
			with self._lock:
				self._db.close()
				self._db = None
