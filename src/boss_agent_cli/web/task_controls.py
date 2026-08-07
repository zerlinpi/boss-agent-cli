"""Cooperative cancellation controls for recruiter Web background tasks."""

from __future__ import annotations

from concurrent.futures import Future
from copy import deepcopy
from importlib.resources import files
from threading import Event
from typing import Any, Callable
from urllib.parse import unquote
from uuid import uuid4

from boss_agent_cli.web import controller as controller_module

_MANAGER_INSTALLED = False
_SERVER_INSTALLED = False


class TaskCancelledError(RuntimeError):
	"""Internal signal used to stop a cooperative Web task."""

	code = "TASK_CANCELLED"

	def __init__(self) -> None:
		super().__init__("任务已取消")


def install_task_manager_controls(tasks_module: Any) -> None:
	"""Add queued cancellation and cooperative running cancellation to TaskManager."""
	global _MANAGER_INSTALLED
	if _MANAGER_INSTALLED:
		return
	_MANAGER_INSTALLED = True

	manager_cls = tasks_module.TaskManager
	original_load_from_db = manager_cls._load_from_db
	original_prune = manager_cls._prune_locked
	original_delete_for_job = manager_cls.delete_for_job

	def ensure_state(self: Any) -> None:
		if not hasattr(self, "_boss_cancel_events"):
			self._boss_cancel_events: dict[str, Event] = {}
			self._boss_futures: dict[str, Future[Any]] = {}
			self._boss_closed = False

	def cancellation_requested(self: Any, task_id: str) -> bool:
		ensure_state(self)
		event = self._boss_cancel_events.get(task_id)
		return bool(event and event.is_set())

	def finish_cancel(self: Any, task_id: str, *, message: str = "任务已取消") -> dict[str, Any] | None:
		with self._lock:
			task = self._tasks.get(task_id)
			if task is None:
				return None
			if task.get("status") == "completed":
				return deepcopy(task)
			task.update({
				"status": "failed",
				"message": message,
				"error": {"code": "TASK_CANCELLED", "message": message},
				"result": None,
				"updated_at": tasks_module._now(),
			})
			self._persist(task)
			return deepcopy(task)

	def load_from_db(self: Any) -> None:
		original_load_from_db(self)
		for task in self._tasks.values():
			if task.get("status") != "cancelling":
				continue
			task.update({
				"status": "failed",
				"message": "服务重启，取消中的任务已终止",
				"error": {"code": "TASK_CANCELLED", "message": "服务重启，取消中的任务已终止"},
				"result": None,
				"updated_at": tasks_module._now(),
			})
			self._persist(task)

	def submit(
		self: Any,
		kind: str,
		function: Callable[[Callable[[int, str], None]], dict[str, Any]],
		*,
		metadata: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		ensure_state(self)
		if self._boss_closed:
			raise RuntimeError("任务管理器已关闭")
		task_id = f"task_{uuid4().hex[:12]}"
		task = {
			"id": task_id,
			"kind": kind,
			"status": "queued",
			"progress": 0,
			"message": "等待执行",
			"created_at": tasks_module._now(),
			"updated_at": tasks_module._now(),
			"result": None,
			"error": None,
			"metadata": metadata or {},
		}
		event = Event()
		with self._lock:
			self._tasks[task_id] = task
			self._boss_cancel_events[task_id] = event
			self._persist(task)
			self._prune_locked()
		future = self._executor.submit(self._run, task_id, function)
		with self._lock:
			self._boss_futures[task_id] = future
			if event.is_set():
				future.cancel()
		return deepcopy(task)

	def cancel(self: Any, task_id: str) -> dict[str, Any] | None:
		ensure_state(self)
		with self._lock:
			task = self._tasks.get(task_id)
			if task is None:
				return None
			if task.get("status") in {"completed", "failed"}:
				return deepcopy(task)
			event = self._boss_cancel_events.setdefault(task_id, Event())
			event.set()
			future = self._boss_futures.get(task_id)
			cancelled_before_start = bool(future is not None and future.cancel())
			if cancelled_before_start:
				task.update({
					"status": "failed",
					"message": "任务已取消",
					"error": {"code": "TASK_CANCELLED", "message": "任务已取消"},
					"result": None,
					"updated_at": tasks_module._now(),
				})
			else:
				task.update({
					"status": "cancelling",
					"message": "正在取消任务，等待当前操作返回",
					"error": {"code": "TASK_CANCEL_REQUESTED", "message": "取消请求已提交"},
					"updated_at": tasks_module._now(),
				})
			self._persist(task)
			return deepcopy(task)

	def run(self: Any, task_id: str, function: Callable[..., dict[str, Any]]) -> None:
		ensure_state(self)
		if cancellation_requested(self, task_id):
			finish_cancel(self, task_id)
			return
		self._update(task_id, status="running", progress=1, message="正在执行")

		def progress(value: int, message: str) -> None:
			if cancellation_requested(self, task_id):
				raise TaskCancelledError()
			self._update(task_id, progress=max(0, min(int(value), 100)), message=message)

		try:
			result = function(progress)
		except TaskCancelledError:
			finish_cancel(self, task_id)
			return
		except Exception as exc:
			if cancellation_requested(self, task_id):
				finish_cancel(self, task_id)
				return
			code = getattr(exc, "code", exc.__class__.__name__)
			self._update(
				task_id,
				status="failed",
				message=str(exc),
				error={"code": str(code), "message": str(exc)},
			)
			return
		if cancellation_requested(self, task_id):
			finish_cancel(self, task_id)
			return
		self._update(
			task_id,
			status="completed",
			progress=100,
			message="执行完成",
			result=result,
		)

	def has_active_screening(self: Any, job_key: str | None = None) -> bool:
		ensure_state(self)
		with self._lock:
			for task in self._tasks.values():
				if task.get("status") not in {"queued", "running", "cancelling"}:
					continue
				if task.get("kind") not in {"screen-local", "screen-boss"}:
					continue
				metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
				result = task.get("result") if isinstance(task.get("result"), dict) else {}
				task_job_key = str(metadata.get("job_key") or result.get("job_key") or "")
				if job_key is None or not task_job_key or task_job_key == job_key:
					return True
		return False

	def prune_locked(self: Any) -> None:
		ensure_state(self)
		original_prune(self)
		alive = set(self._tasks)
		for task_id in list(self._boss_cancel_events):
			if task_id not in alive:
				self._boss_cancel_events.pop(task_id, None)
				self._boss_futures.pop(task_id, None)

	def delete_for_job(self: Any, job_key: str) -> int:
		ensure_state(self)
		result = original_delete_for_job(self, job_key)
		alive = set(self._tasks)
		for task_id in list(self._boss_cancel_events):
			if task_id not in alive:
				self._boss_cancel_events.pop(task_id, None)
				self._boss_futures.pop(task_id, None)
		return result

	def close(self: Any) -> None:
		ensure_state(self)
		with self._lock:
			self._boss_closed = True
			for task_id, task in self._tasks.items():
				if task.get("status") not in {"queued", "running", "cancelling"}:
					continue
				event = self._boss_cancel_events.setdefault(task_id, Event())
				event.set()
				future = self._boss_futures.get(task_id)
				if future is not None:
					future.cancel()
				task.update({
					"status": "failed",
					"message": "服务关闭，任务已取消",
					"error": {"code": "TASK_CANCELLED", "message": "服务关闭，任务已取消"},
					"result": None,
					"updated_at": tasks_module._now(),
				})
				self._persist(task)
		self._executor.shutdown(wait=False, cancel_futures=True)
		with self._lock:
			self._close_database()

	setattr(manager_cls, "_load_from_db", load_from_db)
	setattr(manager_cls, "submit", submit)
	setattr(manager_cls, "_run", run)
	setattr(manager_cls, "cancel", cancel)
	setattr(manager_cls, "has_active_screening", has_active_screening)
	setattr(manager_cls, "_prune_locked", prune_locked)
	setattr(manager_cls, "delete_for_job", delete_for_job)
	setattr(manager_cls, "close", close)


def install_task_control_server(server_module: Any) -> None:
	"""Expose cancellation through the loopback API and inject the cancel control UI."""
	global _SERVER_INSTALLED
	if _SERVER_INSTALLED:
		return
	_SERVER_INSTALLED = True

	application_cls = server_module.RecruiterWebApplication
	original_post: Callable[..., Any] = application_cls.post
	original_asset: Callable[..., tuple[bytes, str]] = application_cls.asset

	def post(self: Any, path: str, payload: dict[str, Any]) -> Any:
		if path.startswith("/api/tasks/") and path.endswith("/cancel"):
			task_id = unquote(path[len("/api/tasks/"):-len("/cancel")].strip("/"))
			if not task_id:
				raise controller_module.WebConsoleError("INVALID_PARAM", "任务 ID 不能为空")
			result = self.tasks.cancel(task_id)
			if result is None:
				raise controller_module.WebConsoleError("TASK_NOT_FOUND", "任务不存在", status=404)
			return result
		return original_post(self, path, payload)

	def asset(self: Any, name: str) -> tuple[bytes, str]:
		content, content_type = original_asset(self, name)
		if name == "app.js":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("task_controls.js").read_bytes()
		return content, content_type

	setattr(application_cls, "post", post)
	setattr(application_cls, "asset", asset)
