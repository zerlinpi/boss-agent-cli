"""Install local data-lifecycle and reliability extensions for the Web console."""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from typing import Any, Callable
from urllib.parse import urlparse

import boss_agent_cli.recruiter_ai_store as recruiter_store_module
from boss_agent_cli.recruiter_ai import RecruiterAIError, candidate_name
from boss_agent_cli.recruiter_ai_models import stable_hash
from boss_agent_cli.web import controller as controller_module
from boss_agent_cli.web.deletion import delete_candidate_data, delete_job_data
from boss_agent_cli.web.tasks import TaskManager

_INSTALLED = False
_SERVER_INSTALLED = False
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _authority_host(authority: str) -> str:
	value = authority.strip().lower()
	if value.startswith("["):
		end = value.find("]")
		return value[:end + 1] if end >= 0 else value
	return value.rsplit(":", 1)[0] if ":" in value else value


def is_loopback_authority(authority: str) -> bool:
	return _authority_host(authority) in _LOOPBACK_HOSTS


def is_loopback_origin(origin: str) -> bool:
	if not origin:
		return True
	try:
		parsed = urlparse(origin)
	except ValueError:
		return False
	return parsed.scheme == "http" and (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}


def install_controller_extensions() -> None:
	"""Add irreversible local deletion, stable file identity, and safe audit behavior."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_save_job = controller_cls.save_job

	def save_job(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		if not payload.get("_delete"):
			return original_save_job(self, payload)
		job_key = controller_module._safe_identifier(str(payload.get("job_key") or ""), label="岗位标识")
		try:
			result = delete_job_data(self.store, job_key)
		except RecruiterAIError as exc:
			raise controller_module.WebConsoleError("JOB_DELETE_FAILED", str(exc), status=404) from exc
		self.audit.append(
			"job.deleted",
			entity_type="job",
			entity_id=job_key,
			summary="已删除岗位及关联的本地候选人数据",
			metadata={
				"evaluation_count": result["evaluation_count"],
				"reply_count": result["reply_count"],
			},
		)
		return result

	def mark_candidate(self: Any, evaluation_id: str, status: str, note: str = "") -> dict[str, Any]:
		evaluation_id = controller_module._safe_identifier(evaluation_id, label="候选人评估 ID")
		if status == "__delete__":
			try:
				result = delete_candidate_data(self.store, evaluation_id)
			except RecruiterAIError as exc:
				raise controller_module.WebConsoleError("CANDIDATE_DELETE_FAILED", str(exc), status=404) from exc
			self.audit.append(
				"candidate.deleted",
				entity_type="candidate",
				entity_id=evaluation_id,
				summary="已删除候选人的本地评估和回复数据",
				metadata={
					"evaluation_count": result["evaluation_count"],
					"reply_count": result["reply_count"],
				},
			)
			return result
		try:
			record = self.store.set_status(evaluation_id, status, note=note)
		except RecruiterAIError as exc:
			raise controller_module.WebConsoleError("STATUS_UPDATE_FAILED", str(exc)) from exc
		self.audit.append(
			"candidate.status.updated",
			entity_type="candidate",
			entity_id=evaluation_id,
			summary=f"候选人状态更新为 {status}",
			metadata={"status": status, "note_present": bool(note)},
		)
		return record

	setattr(controller_cls, "save_job", save_job)
	setattr(controller_cls, "mark_candidate", mark_candidate)
	_install_stable_web_candidate_key()
	_install_sqlite_pragmas()


def _install_stable_web_candidate_key() -> None:
	original_candidate_key = recruiter_store_module.candidate_key
	if getattr(original_candidate_key, "_boss_web_stable", False):
		return

	def candidate_key(resume: dict[str, Any], source: dict[str, Any] | None = None) -> str:
		source = source or {}
		filename = str(source.get("filename") or "").strip().lower()
		if source.get("type") == "web-upload" and filename:
			identity = {
				"filename": filename,
				"name": candidate_name(resume).strip().lower(),
			}
			return f"web-upload:{stable_hash(identity)[:24]}"
		return original_candidate_key(resume, source)

	setattr(candidate_key, "_boss_web_stable", True)
	setattr(recruiter_store_module, "candidate_key", candidate_key)


def _install_sqlite_pragmas() -> None:
	original_init = TaskManager.__init__
	if getattr(original_init, "_boss_lifecycle_wrapped", False):
		return

	def init(self: Any, *args: Any, **kwargs: Any) -> None:
		original_init(self, *args, **kwargs)
		database = getattr(self, "_db", None)
		if database is None:
			return
		try:
			database.execute("PRAGMA journal_mode=WAL")
			database.execute("PRAGMA synchronous=NORMAL")
			database.execute("PRAGMA busy_timeout=5000")
			database.commit()
		except sqlite3.Error:
			return

	setattr(init, "_boss_lifecycle_wrapped", True)
	setattr(TaskManager, "__init__", init)


def install_server_extensions(server_module: Any) -> None:
	"""Append lifecycle assets and enforce loopback-only Host/Origin requests."""
	global _SERVER_INSTALLED
	if _SERVER_INSTALLED:
		return
	_SERVER_INSTALLED = True
	application_cls = server_module.RecruiterWebApplication
	original_asset: Callable[..., tuple[bytes, str]] = application_cls.asset

	def asset(self: Any, name: str) -> tuple[bytes, str]:
		content, content_type = original_asset(self, name)
		if name == "app.js":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("lifecycle.js").read_bytes()
		elif name == "styles.css":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("lifecycle.css").read_bytes()
		return content, content_type

	setattr(application_cls, "asset", asset)

	handler_cls = server_module.RecruiterRequestHandler
	original_get = handler_cls.do_GET
	original_post = handler_cls.do_POST

	def request_allowed(handler: Any) -> bool:
		if is_loopback_authority(handler.headers.get("Host", "")) and is_loopback_origin(handler.headers.get("Origin", "")):
			return True
		handler._send_error(controller_module.WebConsoleError(
			"INVALID_LOCAL_ORIGIN",
			"Web 控制台只接受本机回环地址请求",
			status=403,
		))
		return False

	def do_get(self: Any) -> None:
		if request_allowed(self):
			original_get(self)

	def do_post(self: Any) -> None:
		if request_allowed(self):
			original_post(self)

	setattr(handler_cls, "do_GET", do_get)
	setattr(handler_cls, "do_POST", do_post)
