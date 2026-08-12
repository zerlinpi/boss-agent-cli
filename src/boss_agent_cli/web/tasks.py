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
_CORRUPT_DB_MARKERS = ("malformed", "file is not a database", "database disk image")


def _now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _restrict_permissions(path: Path, mode: int) -> None:
	try:
		path.chmod(mode)
	except OSError:
		pass


def _is_corrupt_database_error(exc: sqlite3.DatabaseError) -> bool:
	message = str(exc).lower()
	return any(marker in message for marker in _CORRUPT_DB_MARKERS)


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
			_restrict_permissions(storage_path.parent, 0o700)
			try:
				self._open_database(storage_path)
			except sqlite3.DatabaseError as exc:
				if not _is_corrupt_database_error(exc):
					self._close_database()
					raise
				self._recover_corrupt_database(storage_path)
				self._open_database(storage_path)

	def _open_database(self, storage_path: Path) -> None:
		self._db = sqlite3.connect(storage_path, check_same_thread=False, timeout=5.0)
		_restrict_permissions(storage_path, 0o600)
		self._db.row_factory = sqlite3.Row
		self._initialize_db()
		self._load_from_db()

	def _close_database(self) -> None:
		if self._db is None:
			return
		try:
			self._db.close()
		except sqlite3.Error:
			pass
		self._db = None

	def _recover_corrupt_database(self, storage_path: Path) -> None:
		"""Quarantine a confirmed-corrupt task DB and rebuild only task history storage."""
		self._close_database()
		stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
		quarantine = storage_path.with_name(f"{storage_path.name}.corrupt-{stamp}-{uuid4().hex[:6]}")
		if storage_path.exists():
			storage_path.replace(quarantine)
			_restrict_permissions(quarantine, 0o600)
		for suffix in ("-wal", "-shm"):
			try:
				Path(f"{storage_path}{suffix}").unlink()
			except FileNotFoundError:
				pass

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
		rows = self._db.execute("SELECT * FROM web_tasks ORDER BY created_at DESC LIMIT ?", (self._max_tasks,)).fetchall()
		for row in rows:
			task = self._row_to_task(row)
			if task["status"] in {"queued", "running"}:
				task.update({
					"status": "failed",
					"message": "服务重启前任务未完成",
					"error": {"code": "TASK_INTERRUPTED", "message": "服务重启导致任务中断"},
					"updated_at": _now(),
				})
				self._persist(task)
			elif task["status"] == "cancelling":
				task.update({
					"status": "failed",
					"message": "任务已取消",
					"error": {"code": "TASK_CANCELLED", "message": "任务在服务重启前已请求取消"},
					"updated_at": _now(),
				})
				self._persist(task)
			self._tasks[task["id"]] = task

	@staticmethod
	def _safe_json(value: Any, fallback: Any) -> Any:
		if value in (None, ""):
			return deepcopy(fallback)
		try:
			parsed = json.loads(value)
		except (TypeError, ValueError, json.JSONDecodeError):
			return deepcopy(fallback)
		return parsed

	@classmethod
	def _row_to_task(cls, row: sqlite3.Row) -> dict[str, Any]:
		return {
			"id": row["id"],
			"kind": row["kind"],
			"status": row["status"],
			"progress": row["progress"],
			"message": row["message"],
			"created_at": row["created_at"],
			"updated_at": row["updated_at"],
			"result": cls._safe_json(row["result_json"], None),
			"error": cls._safe_json(row["error_json"], None),
			"metadata": cls._safe_json(row["metadata_json"], {}),
		}

	def _persist(self, task: dict[str, Any]) -> None:
		if self._db is None:
			return
		self._db.execute(
			"""
			INSERT INTO web_tasks (
				id, kind, status, progress, message, created_at, updated_at,
				result_json, error_json, metadata_json
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(id) DO UPDATE SET
				kind=excluded.kind,
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

	def submit(
		self,
		kind: str,
		fn: TaskFunction,
		*,
		metadata: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		task_id = f"task_{uuid4().hex[:12]}"
		now = _now()
		task = {
			"id": task_id,
			"kind": kind,
			"status": "queued",
			"progress": 0,
			"message": "任务已进入队列",
			"created_at": now,
			"updated_at": now,
			"result": None,
			"error": None,
			"metadata": metadata or {},
		}
		with self._lock:
			self._tasks[task_id] = task
			self._trim_locked()
			self._persist(task)

		def progress(value: int, message: str) -> None:
			with self._lock:
				current = self._tasks.get(task_id)
				if current is None:
					return
				current.update({
					"progress": max(0, min(int(value), 100)),
					"message": message,
					"updated_at": _now(),
				})
				self._persist(current)

		def runner() -> None:
			with self._lock:
				current = self._tasks.get(task_id)
				if current is None:
					return
				current.update({"status": "running", "message": "任务执行中", "updated_at": _now()})
				self._persist(current)
			try:
				result = fn(progress)
			except Exception as exc:  # noqa: BLE001
				with self._lock:
					current = self._tasks.get(task_id)
					if current is None:
						return
					current.update({
						"status": "failed",
						"message": str(exc),
						"updated_at": _now(),
						"error": {
							"code": getattr(exc, "code", "TASK_FAILED"),
							"message": str(exc),
						},
					})
					self._persist(current)
				return
			with self._lock:
				current = self._tasks.get(task_id)
				if current is None:
					return
				current.update({
					"status": "completed",
					"progress": 100,
					"message": "任务执行完成",
					"updated_at": _now(),
					"result": result,
				})
				self._persist(current)

		self._executor.submit(runner)
		return deepcopy(task)

	def _trim_locked(self) -> None:
		if len(self._tasks) <= self._max_tasks:
			return
		completed = [
			item for item in self._tasks.values()
			if item["status"] in {"completed", "failed"}
		]
		completed.sort(key=lambda item: item["updated_at"])
		for item in completed[: max(0, len(self._tasks) - self._max_tasks)]:
			self._tasks.pop(item["id"], None)
			if self._db is not None:
				self._db.execute("DELETE FROM web_tasks WHERE id = ?", (item["id"],))
		if self._db is not None:
			self._db.commit()

	def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
		with self._lock:
			items = sorted(self._tasks.values(), key=lambda item: item["created_at"], reverse=True)
			return deepcopy(items[: max(1, min(limit, self._max_tasks))])

	def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
		"""Compatibility alias for callers that request recent task history."""
		return self.list(limit=limit)

	def get(self, task_id: str) -> dict[str, Any]:
		with self._lock:
			if task_id not in self._tasks:
				raise KeyError(task_id)
			return deepcopy(self._tasks[task_id])

	def scrub_evaluations(self, evaluation_ids: set[str], *, job_key: str | None = None) -> dict[str, int]:
		"""Remove deleted evaluation references from persisted task history.

		When deleting an entire job, callers pass ``job_key`` so even summary-only task rows for that job
		are removed. Candidate-level deletion keeps unrelated task history but scrubs candidate-specific
		items and identifiers from nested results.
		"""
		identifiers = {str(value) for value in evaluation_ids if str(value)}
		updated = 0
		deleted = 0
		with self._lock:
			for task_id in list(self._tasks):
				task = self._tasks[task_id]
				raw_metadata = task.get("metadata")
				metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
				if job_key and str(metadata.get("job_key") or "") == job_key:
					self._tasks.pop(task_id, None)
					if self._db is not None:
						self._db.execute("DELETE FROM web_tasks WHERE id = ?", (task_id,))
					deleted += 1
					continue
				result, changed = _scrub_result(task.get("result"), identifiers)
				if not changed:
					continue
				task["result"] = result
				task["updated_at"] = _now()
				self._persist(task)
				updated += 1
			if self._db is not None:
				self._db.commit()
		return {"updated": updated, "deleted": deleted}

	def close(self, *, wait: bool = False) -> None:
		self._executor.shutdown(wait=wait, cancel_futures=True)
		with self._lock:
			self._close_database()
