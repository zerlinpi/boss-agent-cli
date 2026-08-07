"""Reliability guards for the recruiter Web workspace.

This module keeps compatibility fixes small and isolated from the large Web
controller. It is installed once by :mod:`boss_agent_cli.web`.
"""

from __future__ import annotations

import json
import math
import statistics
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False
_ALLOWED_REPLY_INTENTS = {
	"auto", "acknowledge", "ask_followup", "invite_interview", "clarify", "decline_draft",
}
_SCREEN_SEEN: ContextVar[set[str] | None] = ContextVar("boss_recruiter_screen_seen", default=None)
MAX_JD_CHARS = 100_000
MAX_MODEL_NAME_CHARS = 256
MAX_API_KEY_CHARS = 8_192
MAX_BASE_URL_CHARS = 2_048


class _LazyAIService:
	"""Resolve the configured AI service only when the first model call is made."""

	def __init__(self, controller: Any, resolver: Callable[[Any], Any]):
		self._controller = controller
		self._resolver = resolver
		self._resolved: Any | None = None

	def _service(self) -> Any:
		if self._resolved is None:
			self._resolved = self._resolver(self._controller)
		return self._resolved

	def chat(self, *args: Any, **kwargs: Any) -> str:
		return str(self._service().chat(*args, **kwargs))


def _as_utc(value: Any) -> datetime | None:
	"""Parse current and legacy timestamps into an aware UTC datetime."""
	try:
		parsed = datetime.fromisoformat(str(value or ""))
	except (TypeError, ValueError):
		return None
	if parsed.tzinfo is None:
		return parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


def _finite_number(value: Any) -> float | None:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return None
	number = float(value)
	return number if math.isfinite(number) else None


def _normalize_friend_id(value: Any) -> int | None:
	"""Return the integer friend id required by chat_history, or None when malformed."""
	if isinstance(value, bool) or value in (None, ""):
		return None
	try:
		parsed = int(str(value).strip())
	except (TypeError, ValueError):
		return None
	return parsed if parsed > 0 else None


def _normalize_record_source(record: dict[str, Any]) -> dict[str, Any]:
	"""Make legacy stored platform references safe to consume without rewriting history."""
	source = record.get("source")
	if isinstance(source, dict):
		clean_source = dict(source)
		clean_source["friend_id"] = _normalize_friend_id(clean_source.get("friend_id"))
		clean = dict(record)
		clean["source"] = clean_source
		return clean
	return record


def _candidate_identity_key(ref: dict[str, Any]) -> str | None:
	"""Build a stable per-screening identity without relying on candidate display names."""
	for field in ("geek_id", "security_id", "friend_id"):
		value = ref.get(field)
		if value not in (None, ""):
			return f"{field}:{value}"
	return None


def _dedupe_candidate_items(
	items: list[dict[str, Any]],
	seen: set[str],
	ref_parser: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
	result: list[dict[str, Any]] = []
	for item in items:
		try:
			key = _candidate_identity_key(ref_parser(item))
		except (TypeError, ValueError, KeyError):
			key = None
		if key is not None:
			if key in seen:
				continue
			seen.add(key)
		result.append(item)
	return result


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int, label: str) -> int:
	if value in (None, ""):
		return default
	if isinstance(value, bool):
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是整数")
	try:
		parsed = int(value)
	except (TypeError, ValueError) as exc:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是整数") from exc
	if not minimum <= parsed <= maximum:
		raise controller_module.WebConsoleError(
			"INVALID_PARAM", f"{label} 必须在 {minimum}-{maximum} 之间"
		)
	return parsed


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float, label: str) -> float:
	if value in (None, ""):
		return default
	if isinstance(value, bool):
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是数字")
	try:
		parsed = float(value)
	except (TypeError, ValueError) as exc:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是数字") from exc
	if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
		raise controller_module.WebConsoleError(
			"INVALID_PARAM", f"{label} 必须是 {minimum}-{maximum} 之间的有限数字"
		)
	return parsed


def _boolean(value: Any, *, default: bool = False, label: str) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	if value in (0, 1):
		return bool(value)
	if isinstance(value, str):
		normalized = value.strip().lower()
		if normalized in {"true", "1", "yes", "on"}:
			return True
		if normalized in {"false", "0", "no", "off", ""}:
			return False
	raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是布尔值")


def _bounded_text(value: Any, *, maximum: int, label: str, allow_empty: bool = True) -> str:
	text = str(value or "").strip()
	if not allow_empty and not text:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 不能为空")
	if len(text) > maximum:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 过长，最多 {maximum} 字符")
	return text


def _validated_base_url(value: Any) -> str | None:
	text = _bounded_text(value, maximum=MAX_BASE_URL_CHARS, label="Base URL")
	if not text:
		return None
	parsed = urlparse(text)
	if parsed.scheme not in {"http", "https"} or not parsed.netloc:
		raise controller_module.WebConsoleError("INVALID_BASE_URL", "Base URL 必须是完整的 HTTP(S) 地址")
	if parsed.username or parsed.password:
		raise controller_module.WebConsoleError("INVALID_BASE_URL", "Base URL 不应包含用户名或密码")
	return text


def install_controller_reliability() -> None:
	"""Install lazy AI resolution, bounded APIs, stable refs, and legacy-safe analytics."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	store_cls = controller_module.RecruiterAIStore
	original_service = controller_cls._service
	original_extract_candidate_ref = controller_module.extract_candidate_ref
	original_candidate_items = controller_module.candidate_items
	original_screen_local = controller_cls.screen_local
	original_screen_boss = controller_cls.screen_boss
	original_generate_reply = controller_cls.generate_reply
	original_configure_ai = controller_cls.configure_ai
	original_save_job = controller_cls.save_job
	original_analyze_job = controller_cls.analyze_job
	original_rank = store_cls.rank
	original_get_evaluation = store_cls.get_evaluation

	def lazy_service(self: Any) -> _LazyAIService:
		return _LazyAIService(self, original_service)

	def extract_candidate_ref(item: dict[str, Any], *, default_job_id: str | None = None) -> dict[str, Any]:
		ref = original_extract_candidate_ref(item, default_job_id=default_job_id)
		ref["friend_id"] = _normalize_friend_id(ref.get("friend_id"))
		return ref

	def candidate_items(payload: Any) -> list[dict[str, Any]]:
		items = original_candidate_items(payload)
		seen = _SCREEN_SEEN.get()
		if seen is None:
			return items
		return _dedupe_candidate_items(items, seen, original_extract_candidate_ref)

	def rank(self: Any, *, job_key: str, top: int) -> list[dict[str, Any]]:
		return [_normalize_record_source(record) for record in original_rank(self, job_key=job_key, top=top)]

	def get_evaluation(self: Any, record_id: str) -> dict[str, Any]:
		return _normalize_record_source(original_get_evaluation(self, record_id))

	def configure_ai(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		clean = dict(payload)
		clean["provider"] = _bounded_text(clean.get("provider"), maximum=64, label="provider", allow_empty=False)
		clean["model"] = _bounded_text(
			clean.get("model"), maximum=MAX_MODEL_NAME_CHARS, label="模型名称", allow_empty=False
		)
		clean["base_url"] = _validated_base_url(clean.get("base_url"))
		clean["api_key"] = _bounded_text(clean.get("api_key"), maximum=MAX_API_KEY_CHARS, label="API Key")
		clean["temperature"] = _bounded_float(
			clean.get("temperature"), default=0.2, minimum=0.0, maximum=2.0, label="temperature"
		)
		clean["max_tokens"] = _bounded_int(
			clean.get("max_tokens"), default=4096, minimum=256, maximum=32768, label="max_tokens"
		)
		return original_configure_ai(self, clean)

	def save_job(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		if payload.get("_delete"):
			return original_save_job(self, payload)
		clean = dict(payload)
		clean["jd_text"] = _bounded_text(clean.get("jd_text"), maximum=MAX_JD_CHARS, label="JD", allow_empty=False)
		clean["title"] = _bounded_text(clean.get("title"), maximum=200, label="岗位名称")
		clean["boss_job_id"] = _bounded_text(clean.get("boss_job_id"), maximum=256, label="BOSS 职位 ID")
		return original_save_job(self, clean)

	def analyze_job(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		clean = dict(payload)
		clean["jd_text"] = _bounded_text(clean.get("jd_text"), maximum=MAX_JD_CHARS, label="JD", allow_empty=False)
		return original_analyze_job(self, clean, progress=progress)

	def screen_local(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		clean = dict(payload)
		clean["force"] = _boolean(clean.get("force"), label="force")
		return original_screen_local(self, clean, progress=progress)

	def screen_boss(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		clean = dict(payload)
		clean["pages"] = _bounded_int(clean.get("pages"), default=1, minimum=1, maximum=10, label="pages")
		clean["limit"] = _bounded_int(clean.get("limit"), default=30, minimum=1, maximum=100, label="limit")
		clean["draft_top"] = _bounded_int(
			clean.get("draft_top"), default=0, minimum=0, maximum=20, label="draft_top"
		)
		clean["force"] = _boolean(clean.get("force"), label="force")
		clean["include_chat"] = _boolean(clean.get("include_chat"), label="include_chat")
		token = _SCREEN_SEEN.set(set())
		try:
			return original_screen_boss(self, clean, progress=progress)
		finally:
			_SCREEN_SEEN.reset(token)

	def generate_reply(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		clean = dict(payload)
		intent = str(clean.get("intent") or "auto").strip()
		if intent not in _ALLOWED_REPLY_INTENTS:
			raise controller_module.WebConsoleError("INVALID_REPLY_INPUT", f"不支持的回复意图: {intent}")
		conversation = str(clean.get("conversation") or "")
		if len(conversation) > 200_000:
			raise controller_module.WebConsoleError("INVALID_REPLY_INPUT", "聊天上下文不能超过 200000 字符")
		clean["intent"] = intent
		clean["conversation"] = conversation
		return original_generate_reply(self, clean)

	def analytics(self: Any, job_key: str) -> dict[str, Any]:
		records = list(self.store.latest_by_candidate(job_key=job_key).values())
		scores: list[float] = []
		confidences: list[float] = []
		recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
		recent = 0
		for record in records:
			evaluation = record.get("evaluation")
			if isinstance(evaluation, dict):
				score = _finite_number(evaluation.get("total_score"))
				confidence = _finite_number(evaluation.get("confidence"))
				if score is not None:
					scores.append(score)
				if confidence is not None:
					confidences.append(confidence)
			created = _as_utc(record.get("created_at"))
			if created is not None and created >= recent_cutoff:
				recent += 1

		distribution = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
		for score in scores:
			if score < 50:
				distribution["0-49"] += 1
			elif score < 70:
				distribution["50-69"] += 1
			elif score < 85:
				distribution["70-84"] += 1
			else:
				distribution["85-100"] += 1

		report = self.store.report(job_key=job_key, top=10)
		status_counts = report.get("status_counts", {})
		total = len(records)
		interviewed = int(status_counts.get("interview", 0)) + int(status_counts.get("hired", 0))
		return {
			"total": total,
			"average_score": round(statistics.mean(scores), 1) if scores else 0,
			"median_score": round(statistics.median(scores), 1) if scores else 0,
			"average_confidence": round(statistics.mean(confidences), 3) if confidences else 0,
			"recent_7d": recent,
			"interview_conversion": round(interviewed / total * 100, 1) if total else 0,
			"score_distribution": distribution,
		}

	def replies(self: Any, *, evaluation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
		try:
			bounded_limit = max(1, min(int(limit), 500))
		except (TypeError, ValueError):
			bounded_limit = 100
		items: list[dict[str, Any]] = []
		for path in sorted(self.store.replies_dir.glob("reply_*.json"), reverse=True):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError):
				continue
			if not isinstance(payload, dict):
				continue
			if evaluation_id and payload.get("evaluation_id") != evaluation_id:
				continue
			items.append(payload)
			if len(items) >= bounded_limit:
				break
		return items

	setattr(store_cls, "rank", rank)
	setattr(store_cls, "get_evaluation", get_evaluation)
	setattr(controller_cls, "_service", lazy_service)
	setattr(controller_cls, "configure_ai", configure_ai)
	setattr(controller_cls, "save_job", save_job)
	setattr(controller_cls, "analyze_job", analyze_job)
	setattr(controller_cls, "screen_local", screen_local)
	setattr(controller_cls, "screen_boss", screen_boss)
	setattr(controller_cls, "generate_reply", generate_reply)
	setattr(controller_cls, "analytics", analytics)
	setattr(controller_cls, "replies", replies)
	setattr(controller_module, "extract_candidate_ref", extract_candidate_ref)
	setattr(controller_module, "candidate_items", candidate_items)


def install_server_reliability(server_module: Any) -> None:
	"""Validate native ports and normalize login payloads before background task creation."""
	original_build_server = server_module.build_server
	if getattr(original_build_server, "_boss_reliability_wrapped", False):
		return
	application_cls = server_module.RecruiterWebApplication
	original_post = application_cls.post

	def post(self: Any, path: str, payload: dict[str, Any]) -> Any:
		if path != "/api/auth/login":
			return original_post(self, path, payload)
		clean = dict(payload)
		clean["timeout"] = _bounded_int(clean.get("timeout"), default=180, minimum=30, maximum=600, label="timeout")
		clean["force_cdp"] = _boolean(clean.get("force_cdp"), label="force_cdp")
		cookie_source = clean.get("cookie_source")
		if cookie_source is not None and not isinstance(cookie_source, str):
			raise controller_module.WebConsoleError("INVALID_PARAM", "cookie_source 必须是字符串")
		if isinstance(cookie_source, str) and len(cookie_source) > 64:
			raise controller_module.WebConsoleError("INVALID_PARAM", "cookie_source 过长")
		return original_post(self, path, clean)

	def build_server(controller: Any, *, host: str = "127.0.0.1", port: int = 8765) -> Any:
		if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
			raise ValueError("Web 控制台端口必须是 0-65535 的整数（0 仅用于测试时自动分配）")
		return original_build_server(controller, host=host, port=port)

	setattr(application_cls, "post", post)
	setattr(build_server, "_boss_reliability_wrapped", True)
	setattr(server_module, "build_server", build_server)
