"""In-memory background tasks for long-running Web console actions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

TaskFunction = Callable[[Callable[[int, str], None]], dict[str, Any]]


def _now() -> str:
	return datetime.now(timezone.utc).isoformat()


class TaskManager:
	"""Run login and screening jobs without blocking the browser request."""

	def __init__(self, *, max_workers: int = 2, max_tasks: int = 100):
		self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="boss-web")
		self._max_tasks = max_tasks
		self._tasks: dict[str, dict[str, Any]] = {}
		self._lock = Lock()

	def submit(self, kind: str, function: TaskFunction) -> dict[str, Any]:
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
		}
		with self._lock:
			self._tasks[task_id] = task
			self._prune_locked()
		self._executor.submit(self._run, task_id, function)
		return deepcopy(task)

	def _run(self, task_id: str, function: TaskFunction) -> None:
		self._update(task_id, status="running", progress=1, message="正在执行")

		def progress(value: int, message: str) -> None:
			self._update(
				task_id,
				progress=max(0, min(int(value), 100)),
				message=message,
			)

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
			return deepcopy(items[:limit])

	def _prune_locked(self) -> None:
		if len(self._tasks) <= self._max_tasks:
			return
		completed = sorted(
			(
				item for item in self._tasks.values()
				if item.get("status") in {"completed", "failed"}
			),
			key=lambda item: str(item.get("updated_at", "")),
		)
		for item in completed[: max(0, len(self._tasks) - self._max_tasks)]:
			self._tasks.pop(str(item["id"]), None)

	def close(self) -> None:
		self._executor.shutdown(wait=False, cancel_futures=True)
