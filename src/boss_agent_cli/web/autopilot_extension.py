"""Web integration for the recruiter AI autopilot pipeline."""

from __future__ import annotations

from importlib.resources import files
from typing import Any, Callable

from boss_agent_cli.commands._recruiter_platform import get_recruiter_platform_instance
from boss_agent_cli.commands.recruiter import ai_autopilot as _autopilot_module
from boss_agent_cli.commands.recruiter.ai_autopilot import RecruiterAutopilotState
from boss_agent_cli.commands.recruiter.ai_autopilot_freshness import install_autopilot_freshness
from boss_agent_cli.commands.recruiter.ai_autopilot_job_profile import run_profiled_autopilot
from boss_agent_cli.commands.recruiter.ai_autopilot_lease import (
	RecruiterAutopilotBusy,
	recruiter_autopilot_lease,
)
from boss_agent_cli.compliance import require_capability_mode
from boss_agent_cli.web import controller as controller_module

_CONTROLLER_INSTALLED = False
_SERVER_INSTALLED = False
_TASKS_INSTALLED = False

install_autopilot_freshness(_autopilot_module)


def _bounded_int(payload: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
	try:
		value = int(payload.get(key, default))
	except (TypeError, ValueError) as exc:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{key} 必须是整数") from exc
	return max(minimum, min(value, maximum))


def install_autopilot_controller() -> None:
	"""Add run/status methods to RecruiterWebController without duplicating pipeline logic."""
	global _CONTROLLER_INSTALLED
	if _CONTROLLER_INSTALLED:
		return
	_CONTROLLER_INSTALLED = True
	controller_cls = controller_module.RecruiterWebController

	def autopilot_status(self: Any) -> dict[str, Any]:
		state = RecruiterAutopilotState(self.data_dir).payload
		candidates = state.get("candidates")
		return {
			"last_run": state.get("last_run"),
			"tracked_candidates": len(candidates) if isinstance(candidates, dict) else 0,
		}

	def run_recruiter_autopilot(
		self: Any,
		payload: dict[str, Any],
		*,
		progress: Callable[[int, str], None] | None = None,
	) -> dict[str, Any]:
		try:
			require_capability_mode(self.operating_mode(), "recruiter-applications")
			require_capability_mode(self.operating_mode(), "recruiter-resume")
		except ValueError as exc:
			raise controller_module.WebConsoleError("COMPLIANCE_BLOCKED", str(exc), status=409) from exc
		include_chat = bool(payload.get("include_chat", False))
		if include_chat:
			try:
				require_capability_mode(self.operating_mode(), "recruiter-chatmsg")
			except ValueError as exc:
				raise controller_module.WebConsoleError("COMPLIANCE_BLOCKED", str(exc), status=409) from exc

		job_keys_payload = payload.get("job_keys")
		if job_keys_payload is None:
			selected_job_keys = None
		elif isinstance(job_keys_payload, list):
			selected_job_keys = {str(item).strip() for item in job_keys_payload if str(item).strip()}
		else:
			raise controller_module.WebConsoleError("INVALID_PARAM", "job_keys 必须是数组")

		if progress:
			progress(5, "正在读取 BOSS 当前职位并生成/刷新岗位画像")
		service = self._service()
		auth = self._auth()
		try:
			with recruiter_autopilot_lease(self.data_dir):
				with get_recruiter_platform_instance(self._context(), auth) as platform:
					result = run_profiled_autopilot(
						data_dir=self.data_dir,
						platform=platform,
						service=service,
						store=self.store,
						max_pages=_bounded_int(payload, "max_pages", 30, 1, 100),
						max_candidates_per_job=_bounded_int(payload, "max_candidates_per_job", 2000, 1, 10000),
						refresh_seen_hours=_bounded_int(payload, "refresh_seen_hours", 24, 0, 24 * 30),
						top=_bounded_int(payload, "top", 50, 1, 500),
						draft_top=_bounded_int(payload, "draft_top", 10, 0, 100),
						include_chat=include_chat,
						force=bool(payload.get("force", False)),
						auto_configure=bool(payload.get("auto_configure", True)),
						selected_job_keys=selected_job_keys,
					)
		except RecruiterAutopilotBusy as exc:
			raise controller_module.WebConsoleError(exc.code, str(exc), status=409) from exc
		if progress:
			progress(100, "全职位增量同步、AI 评分与草稿生成完成")
		totals = result.get("totals") if isinstance(result.get("totals"), dict) else {}
		self.audit.append(
			"autopilot.completed",
			entity_type="screening",
			entity_id="all-jobs",
			summary=(
				f"Autopilot 完成：{totals.get('jobs_processed', 0)} 个职位，"
				f"新增评估 {totals.get('evaluated', 0)}，失败 {totals.get('failed', 0)}"
			),
			metadata={
				"jobs_processed": totals.get("jobs_processed", 0),
				"evaluated": totals.get("evaluated", 0),
				"failed": totals.get("failed", 0),
				"messages_sent": 0,
			},
		)
		return result

	setattr(controller_cls, "autopilot_status", autopilot_status)
	setattr(controller_cls, "run_recruiter_autopilot", run_recruiter_autopilot)


def install_autopilot_task_safety(tasks_module: Any) -> None:
	"""Treat autopilot as active screening so job deletion cannot race a running global sync."""
	global _TASKS_INSTALLED
	if _TASKS_INSTALLED:
		return
	_TASKS_INSTALLED = True
	manager_cls = tasks_module.TaskManager
	original_has_active_screening = manager_cls.has_active_screening

	def has_active_screening(self: Any, job_key: str | None = None) -> bool:
		with self._lock:
			for task in self._tasks.values():
				if task.get("status") not in {"queued", "running", "cancelling"}:
					continue
				if task.get("kind") == "autopilot":
					return True
		return original_has_active_screening(self, job_key)

	setattr(manager_cls, "has_active_screening", has_active_screening)


def install_autopilot_server(server_module: Any) -> None:
	"""Expose autopilot background tasks and append the no-build Web controls."""
	global _SERVER_INSTALLED
	if _SERVER_INSTALLED:
		return
	_SERVER_INSTALLED = True
	application_cls = server_module.RecruiterWebApplication
	original_get: Callable[..., Any] = application_cls.get
	original_post: Callable[..., Any] = application_cls.post
	original_asset: Callable[..., tuple[bytes, str]] = application_cls.asset

	def get(self: Any, path: str, query: dict[str, list[str]]) -> Any:
		if path == "/api/autopilot/status":
			return self.controller.autopilot_status()
		return original_get(self, path, query)

	def post(self: Any, path: str, payload: dict[str, Any]) -> Any:
		if path == "/api/autopilot/run":
			if self.tasks.has_active_screening():
				raise controller_module.WebConsoleError(
					"SCREENING_ALREADY_RUNNING",
					"已有筛选或 Autopilot 任务正在运行，请等待或取消现有任务",
					status=409,
				)
			return self.tasks.submit(
				"autopilot",
				lambda progress: self.controller.run_recruiter_autopilot(payload, progress=progress),
				metadata={"title": "Recruiter Autopilot · 全职位增量同步"},
			)
		return original_post(self, path, payload)

	def asset(self: Any, name: str) -> tuple[bytes, str]:
		content, content_type = original_asset(self, name)
		if name == "app.js":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("autopilot.js").read_bytes()
		elif name == "styles.css":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("autopilot.css").read_bytes()
		return content, content_type

	server_module._ASYNC_PATHS.add("/api/autopilot/run")
	setattr(application_cls, "get", get)
	setattr(application_cls, "post", post)
	setattr(application_cls, "asset", asset)
