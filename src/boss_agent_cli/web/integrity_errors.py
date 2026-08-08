"""Map recruiter persistence corruption to actionable Web API errors."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.recruiter_ai import RecruiterAIError

_INSTALLED = False
_INTEGRITY_PREFIXES = (
	"评估文件损坏:",
	"评估文件标识不一致:",
	"岗位配置损坏:",
)


def _is_integrity_error(exc: RecruiterAIError) -> bool:
	message = str(exc)
	return any(message.startswith(prefix) for prefix in _INTEGRITY_PREFIXES)


def install_integrity_error_mapping(server_module: Any) -> None:
	"""Convert only persistence corruption errors into a stable Web API contract."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	application_cls = server_module.RecruiterWebApplication
	original_get: Callable[..., Any] = application_cls.get
	original_post: Callable[..., Any] = application_cls.post

	def translate(exc: RecruiterAIError) -> None:
		if not _is_integrity_error(exc):
			raise exc
		raise server_module.WebConsoleError(
			"DATA_INTEGRITY_ERROR",
			f"本地招聘数据完整性检查失败：{exc}",
			status=409,
		) from exc

	def get(self: Any, path: str, query: dict[str, list[str]]) -> Any:
		try:
			return original_get(self, path, query)
		except RecruiterAIError as exc:
			translate(exc)

	def post(self: Any, path: str, payload: dict[str, Any]) -> Any:
		try:
			return original_post(self, path, payload)
		except RecruiterAIError as exc:
			translate(exc)

	setattr(application_cls, "get", get)
	setattr(application_cls, "post", post)
