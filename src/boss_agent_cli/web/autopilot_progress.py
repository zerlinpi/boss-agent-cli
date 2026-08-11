"""Progress/cancellation adapters for long-running Web recruiter autopilot tasks."""

from __future__ import annotations

from typing import Any, Callable


class _ProgressTracker:
	def __init__(self, callback: Callable[[int, str], None]) -> None:
		self.callback = callback
		self.operations = 0

	def checkpoint(self, label: str) -> None:
		self.operations += 1
		# The exact number of candidates is not known before platform pagination. Keep the bar
		# monotonic and reserve 93-100 for persistence/finalization; message text carries the
		# useful completed-operation count. Calling the callback is also a task-cancel checkpoint.
		percent = min(92, 10 + self.operations)
		self.callback(percent, f"{label} · 已完成 {self.operations} 个同步/AI 步骤")


class _PlatformProxy:
	_MONITORED = {
		"list_jobs": "读取 BOSS 职位目录",
		"job_detail": "刷新 BOSS 岗位 JD",
		"friend_list": "读取 BOSS 投递分页",
		"view_geek": "读取候选人简历",
		"chat_history": "读取候选人聊天上下文",
	}

	def __init__(self, target: Any, tracker: _ProgressTracker) -> None:
		self._target = target
		self._tracker = tracker

	def __getattr__(self, name: str) -> Any:
		value = getattr(self._target, name)
		label = self._MONITORED.get(name)
		if not label or not callable(value):
			return value

		def wrapped(*args: Any, **kwargs: Any) -> Any:
			self._tracker.checkpoint(label)
			return value(*args, **kwargs)

		return wrapped


class _ServiceProxy:
	def __init__(self, target: Any, tracker: _ProgressTracker) -> None:
		self._target = target
		self._tracker = tracker

	def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
		self._tracker.checkpoint("调用 AI 分析")
		return str(self._target.chat(messages, **kwargs))


def wrap_autopilot_dependencies(
	platform: Any,
	service: Any,
	progress: Callable[[int, str], None] | None,
) -> tuple[Any, Any]:
	"""Wrap Web-only dependencies so long runs remain observable and cancellable."""
	if progress is None:
		return platform, service
	tracker = _ProgressTracker(progress)
	return _PlatformProxy(platform, tracker), _ServiceProxy(service, tracker)
