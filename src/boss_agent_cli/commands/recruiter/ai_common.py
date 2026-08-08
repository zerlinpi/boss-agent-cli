"""Shared helpers for recruiter AI CLI commands."""

from __future__ import annotations

from typing import Any

import click

from boss_agent_cli.ai.config import AIConfigStore
from boss_agent_cli.ai.service import AIService, AIServiceError, ChatService
from boss_agent_cli.display import handle_error_output
from boss_agent_cli.recruiter_ai import (
	RecruiterAIError,
	RecruiterAIStore,
	candidate_key,
	evaluate_resume,
	generate_reply_draft,
	normalize_resume,
	normalize_rubric,
	read_json_input,
	read_text_input,
	recommended_reply_intent,
	resume_fingerprint,
	rubric_fingerprint,
)

_MAX_RANK_FETCH = 10_000
_CLI_LATEST_CACHE_ATTR = "_boss_cli_latest_candidate_cache"


class AIConfigurationError(AIServiceError):
	"""Raised when recruiter AI configuration is missing or invalid."""

	def __init__(self, message: str, *, recovery_action: str) -> None:
		super().__init__(message)
		self.recovery_action = recovery_action


def _load_service(ctx: click.Context) -> AIService:
	store = AIConfigStore(ctx.obj["data_dir"])
	if not store.is_configured():
		raise AIConfigurationError(
			"AI 服务未配置",
			recovery_action="boss ai config --provider <provider> --model <model> --api-key <key>",
		)
	config = store.load_config()
	api_key, base_url, model = store.get_api_key(), store.get_base_url(), config.get("ai_model")
	if not api_key or not base_url or not isinstance(model, str) or not model.strip():
		raise AIConfigurationError("AI 配置不完整", recovery_action="boss ai config")
	try:
		return AIService(
			base_url=base_url,
			api_key=api_key,
			model=model,
			temperature=float(config.get("ai_temperature", 0.2)),
			max_tokens=int(config.get("ai_max_tokens", 4096)),
		)
	except (AIServiceError, TypeError, ValueError) as exc:
		raise AIConfigurationError(
			f"AI 配置无效: {exc}",
			recovery_action="boss ai config",
		) from exc


class DeferredAIService:
	"""Resolve CLI AI configuration only when the first model request is required."""

	def __init__(self, ctx: click.Context) -> None:
		self._ctx = ctx
		self._resolved: AIService | None = None

	def chat(
		self,
		messages: list[dict[str, Any]],
		*,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> str:
		if self._resolved is None:
			self._resolved = _load_service(self._ctx)
		return self._resolved.chat(messages, temperature=temperature, max_tokens=max_tokens)


def service_for(ctx: click.Context, *, deferred: bool = False) -> ChatService | None:
	if deferred:
		return DeferredAIService(ctx)
	try:
		return _load_service(ctx)
	except AIConfigurationError as exc:
		emit_ai_error(ctx, "recruiter-ai", exc)
		return None


def emit_input_error(ctx: click.Context, message: str) -> None:
	handle_error_output(
		ctx, "recruiter-ai", code="INVALID_PARAM",
		message=message, recoverable=False,
	)


def emit_ai_error(ctx: click.Context, command: str, exc: AIServiceError) -> None:
	if isinstance(exc, AIConfigurationError):
		handle_error_output(
			ctx, command, code="AI_NOT_CONFIGURED",
			message=str(exc), recoverable=True,
			recovery_action=exc.recovery_action,
		)
		return
	handle_error_output(
		ctx, command, code="AI_API_ERROR",
		message=f"AI 服务调用失败: {exc}", recoverable=True,
		recovery_action="检查 AI 配置和网络后重试",
	)


def load_rubric(rubric_input: str | None) -> dict[str, Any]:
	return normalize_rubric(read_json_input(rubric_input)) if rubric_input else normalize_rubric()


def resolve_job(
	store: RecruiterAIStore,
	*,
	job_key: str,
	jd_input: str | None,
	rubric_input: str | None,
) -> tuple[str, dict[str, Any]]:
	if jd_input is not None:
		return read_text_input(jd_input), load_rubric(rubric_input)
	job = store.get_job(job_key)
	jd_text, rubric = job.get("jd_text"), job.get("rubric")
	if not isinstance(jd_text, str) or not jd_text.strip() or not isinstance(rubric, dict):
		raise RecruiterAIError(f"岗位配置缺少 JD 或评分规则: {job_key}")
	return jd_text, load_rubric(rubric_input) if rubric_input else normalize_rubric(rubric)


def _evaluation_directory_mtime(store: RecruiterAIStore) -> int:
	try:
		return store.evaluations_dir.stat().st_mtime_ns
	except OSError:
		return -1


def _latest_candidate_index(store: RecruiterAIStore, job_key: str) -> dict[str, dict[str, Any]]:
	cache = getattr(store, _CLI_LATEST_CACHE_ATTR, None)
	if not isinstance(cache, dict):
		cache = {}
		setattr(store, _CLI_LATEST_CACHE_ATTR, cache)
	mtime = _evaluation_directory_mtime(store)
	entry = cache.get(job_key)
	if isinstance(entry, dict) and entry.get("mtime") == mtime and isinstance(entry.get("items"), dict):
		return entry["items"]
	items = store.latest_by_candidate(job_key=job_key)
	cache[job_key] = {"mtime": mtime, "items": items}
	return items


def _cached_unchanged(
	store: RecruiterAIStore,
	*,
	job_key: str,
	jd_text: str,
	resume: dict[str, Any],
	source: dict[str, Any],
	rubric: dict[str, Any],
) -> dict[str, Any] | None:
	record = _latest_candidate_index(store, job_key).get(candidate_key(resume, source))
	if record is None:
		return None
	if str(record.get("jd_text") or "") != jd_text:
		return None
	if record.get("resume_fingerprint") != resume_fingerprint(resume):
		return None
	if record.get("rubric_fingerprint") != rubric_fingerprint(rubric):
		return None
	return record


def _remember_evaluation(store: RecruiterAIStore, job_key: str, record: dict[str, Any]) -> None:
	cache = getattr(store, _CLI_LATEST_CACHE_ATTR, None)
	if not isinstance(cache, dict):
		return
	entry = cache.get(job_key)
	if not isinstance(entry, dict) or not isinstance(entry.get("items"), dict):
		return
	key = str(record.get("candidate_key") or "")
	if key:
		entry["items"][key] = record
	entry["mtime"] = _evaluation_directory_mtime(store)


def evaluate_local(
	*,
	service: ChatService,
	store: RecruiterAIStore,
	jd_text: str,
	rubric: dict[str, Any],
	resume_payload: dict[str, Any],
	job_key: str,
	source: dict[str, Any],
	save: bool,
	force: bool = False,
) -> dict[str, Any]:
	resume = normalize_resume(resume_payload)
	if save and not force:
		existing = _cached_unchanged(
			store,
			job_key=job_key,
			jd_text=jd_text,
			resume=resume,
			source=source,
			rubric=rubric,
		)
		if existing is not None:
			return {**existing, "saved": True, "skipped": True, "skip_reason": "unchanged"}
	evaluation = evaluate_resume(service, jd_text, resume, rubric)
	if not save:
		return {
			"job_key": job_key, "resume": resume, "evaluation": evaluation,
			"source": source, "saved": False, "skipped": False,
		}
	record = store.save_evaluation(
		job_key=job_key, jd_text=jd_text, resume=resume,
		evaluation=evaluation, source=source, rubric=rubric,
	)
	_remember_evaluation(store, job_key, record)
	record.update({"saved": True, "skipped": False})
	return record


def ranked_records_for_run(
	store: RecruiterAIStore,
	*,
	job_key: str,
	top: int,
	draft_top: int,
	processed_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
	"""Return the display ranking and the ranked subset created by the current invocation.

	Automatic draft generation must never silently include historical candidates. When drafts are
	requested and new evaluations exist, fetch the store's full bounded ranking before filtering so
	a newly evaluated candidate cannot be hidden behind older high-scoring records.
	"""
	fetch_top = _MAX_RANK_FETCH if draft_top > 0 and processed_ids else max(1, top)
	ranked = store.rank(job_key=job_key, top=fetch_top)
	if not processed_ids:
		return ranked, []
	identifiers = set(processed_ids)
	current = [record for record in ranked if str(record.get("id") or "") in identifiers]
	return ranked, current


def platform_error(platform: Any, response: Any, fallback: str) -> str:
	try:
		code, message = platform.parse_error(response)
	except Exception:
		return fallback
	return f"{code}: {message or fallback}"


def draft_for_records(
	*,
	service: ChatService,
	store: RecruiterAIStore,
	platform: Any | None,
	records: list[dict[str, Any]],
	limit: int,
	include_chat: bool,
	conversation_parser: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	drafts: list[dict[str, Any]] = []
	failed: list[dict[str, str]] = []
	for record in records[:limit]:
		evaluation, jd_text, source = record.get("evaluation"), record.get("jd_text"), record.get("source")
		if not isinstance(evaluation, dict) or not isinstance(jd_text, str):
			continue
		conversation = ""
		if include_chat and platform is not None and isinstance(source, dict):
			friend_id = source.get("friend_id")
			if friend_id not in (None, ""):
				try:
					result = platform.chat_history(int(friend_id), count=30, max_msg_id=None)
					if platform.is_success(result):
						conversation = conversation_parser(platform.unwrap_data(result) or {})
					else:
						failed.append({
							"evaluation_id": str(record.get("id", "")),
							"error": platform_error(platform, result, "聊天记录获取失败"),
						})
				except (TypeError, ValueError, NotImplementedError) as exc:
					failed.append({"evaluation_id": str(record.get("id", "")), "error": str(exc)})
		try:
			intent = recommended_reply_intent(evaluation)
			draft = generate_reply_draft(service, jd_text, evaluation, conversation, intent)
			drafts.append(store.save_reply(
				evaluation_id=str(record.get("id", "")), intent=intent,
				conversation=conversation, draft=draft,
			))
		except AIConfigurationError:
			raise
		except (RecruiterAIError, AIServiceError) as exc:
			failed.append({"evaluation_id": str(record.get("id", "")), "error": str(exc)})
	return drafts, failed
