"""Application services used by the local recruiter Web console."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from boss_agent_cli.ai.config import AIConfigStore, PROVIDER_BASE_URLS
from boss_agent_cli.ai.service import AIService, AIServiceError
from boss_agent_cli.auth.health import assess_auth_health
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.commands._recruiter_platform import get_recruiter_platform_instance
from boss_agent_cli.commands.recruiter.resume_parser import parse_resume
from boss_agent_cli.compliance import AVAILABLE_OPERATING_MODES, require_capability_mode
from boss_agent_cli.config import load_config
from boss_agent_cli.output import Logger
from boss_agent_cli.recruiter_ai import (
	CANDIDATE_STATUSES,
	RecruiterAIError,
	RecruiterAIStore,
	candidate_items,
	conversation_to_text,
	evaluate_resume,
	extract_candidate_ref,
	generate_reply_draft,
	normalize_resume,
	normalize_rubric,
	recommended_reply_intent,
	summarize_ranking,
)

ProgressCallback = Callable[[int, str], None]


class WebConsoleError(RuntimeError):
	"""Structured error surfaced by the Web API."""

	def __init__(self, code: str, message: str, *, status: int = 400):
		super().__init__(message)
		self.code = code
		self.status = status


class RecruiterWebController:
	"""Coordinate local persistence, AI calls, login, and BOSS reads."""

	def __init__(
		self,
		data_dir: Path,
		*,
		platform: str = "zhipin",
		cdp_url: str | None = None,
	):
		self.data_dir = data_dir.expanduser().resolve()
		self.data_dir.mkdir(parents=True, exist_ok=True)
		self.platform = platform
		self.cdp_url = cdp_url
		self.logger = Logger("error")
		self.store = RecruiterAIStore(self.data_dir)
		self.ai_store = AIConfigStore(self.data_dir)
		self.config_path = self.data_dir / "config.json"

	def _config(self) -> dict[str, Any]:
		return load_config(self.config_path)

	def _write_config(self, payload: dict[str, Any]) -> None:
		temporary = self.config_path.with_suffix(".json.tmp")
		temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
		temporary.replace(self.config_path)

	def operating_mode(self) -> str:
		return str(self._config().get("operating_mode") or "assisted")

	def _context(self) -> SimpleNamespace:
		config = self._config()
		return SimpleNamespace(obj={
			"data_dir": self.data_dir,
			"logger": self.logger,
			"platform": self.platform,
			"delay": tuple(config.get("request_delay", (1.5, 3.0))),
			"cdp_url": self.cdp_url or config.get("cdp_url"),
			"config": config,
			"role": "recruiter",
		})

	def _auth(self) -> AuthManager:
		return AuthManager(self.data_dir, logger=self.logger, platform=self.platform)

	def _service(self) -> AIService:
		config = self.ai_store.load_config()
		api_key = self.ai_store.get_api_key()
		base_url = self.ai_store.get_base_url()
		model = config.get("ai_model")
		if not api_key or not base_url or not isinstance(model, str) or not model.strip():
			raise WebConsoleError("AI_NOT_CONFIGURED", "请先在设置页面配置 AI 服务。", status=409)
		return AIService(
			base_url=base_url,
			api_key=api_key,
			model=model,
			temperature=float(config.get("ai_temperature", 0.2)),
			max_tokens=int(config.get("ai_max_tokens", 4096)),
		)

	def bootstrap(self) -> dict[str, Any]:
		jobs = self.store.list_jobs()
		ai_config = self.ai_store.load_config()
		return {
			"data_dir": str(self.data_dir),
			"platform": self.platform,
			"operating_mode": self.operating_mode(),
			"available_operating_modes": list(AVAILABLE_OPERATING_MODES),
			"ai": {
				"configured": self.ai_store.is_configured(),
				"provider": ai_config.get("ai_provider"),
				"model": ai_config.get("ai_model"),
				"base_url": self.ai_store.get_base_url(),
				"providers": PROVIDER_BASE_URLS,
			},
			"auth": self.auth_status(),
			"jobs": [self._job_summary(job) for job in jobs],
			"candidate_statuses": sorted(CANDIDATE_STATUSES),
		}

	@staticmethod
	def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
		metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
		return {
			"job_key": job.get("job_key", ""),
			"title": metadata.get("title") or job.get("job_key", ""),
			"boss_job_id": metadata.get("boss_job_id", ""),
			"updated_at": job.get("updated_at", ""),
			"rubric_fingerprint": job.get("rubric_fingerprint", ""),
		}

	def auth_status(self) -> dict[str, Any]:
		auth = self._auth()
		token = auth.check_status()
		health = assess_auth_health(self.data_dir, platform=self.platform, token=token)
		return {
			"logged_in": token is not None,
			"state": health.auth_state,
			"summary": health.summary,
			"health": health.public_summary(),
		}

	def login(
		self,
		*,
		timeout: int = 180,
		cookie_source: str | None = None,
		force_cdp: bool = False,
		progress: ProgressCallback | None = None,
	) -> dict[str, Any]:
		if progress:
			progress(5, "正在启动登录流程，请在弹出的浏览器中完成登录")
		try:
			token = self._auth().login(
				timeout=max(30, min(int(timeout), 600)),
				cookie_source=cookie_source or None,
				cdp_url=self.cdp_url or self._config().get("cdp_url"),
				force_cdp=force_cdp,
			)
		except Exception as exc:
			raise WebConsoleError("LOGIN_FAILED", str(exc), status=502) from exc
		method = token.pop("_method", "unknown") if isinstance(token, dict) else "unknown"
		if progress:
			progress(100, "登录完成")
		return {"message": f"登录成功（{method}）", "auth": self.auth_status()}

	def configure_ai(self, payload: dict[str, Any]) -> dict[str, Any]:
		provider = str(payload.get("provider") or "").strip()
		model = str(payload.get("model") or "").strip()
		base_url = str(payload.get("base_url") or "").strip() or None
		api_key = str(payload.get("api_key") or "").strip()
		if provider not in PROVIDER_BASE_URLS:
			raise WebConsoleError("INVALID_PROVIDER", f"不支持的 AI provider: {provider}")
		if not model:
			raise WebConsoleError("INVALID_MODEL", "模型名称不能为空")
		if provider == "custom" and not base_url:
			raise WebConsoleError("INVALID_BASE_URL", "custom provider 必须填写 Base URL")
		if not api_key and self.ai_store.get_api_key() is None:
			if provider in {"ollama", "vllm"}:
				api_key = "local"
			else:
				raise WebConsoleError("INVALID_API_KEY", "API Key 不能为空")
		self.ai_store.save_config(
			ai_provider=provider,
			ai_model=model,
			ai_base_url=base_url,
			ai_temperature=float(payload.get("temperature", 0.2)),
			ai_max_tokens=int(payload.get("max_tokens", 4096)),
		)
		if api_key:
			self.ai_store.save_api_key(api_key)
		return self.bootstrap()["ai"]

	def set_operating_mode(self, mode: str) -> dict[str, Any]:
		if mode not in AVAILABLE_OPERATING_MODES:
			raise WebConsoleError("INVALID_MODE", f"不支持的运行模式: {mode}")
		config = self._config()
		config["operating_mode"] = mode
		config["low_risk_mode"] = mode != "research"
		self._write_config(config)
		return {"operating_mode": mode}

	def save_job(self, payload: dict[str, Any]) -> dict[str, Any]:
		job_key = str(payload.get("job_key") or "").strip()
		jd_text = str(payload.get("jd_text") or "").strip()
		if not job_key or not jd_text:
			raise WebConsoleError("INVALID_JOB", "岗位标识和 JD 均不能为空")
		rubric_payload = payload.get("rubric")
		if rubric_payload is not None and not isinstance(rubric_payload, dict):
			raise WebConsoleError("INVALID_RUBRIC", "评分规则必须是 JSON 对象")
		metadata = {
			"title": str(payload.get("title") or job_key).strip(),
			"boss_job_id": str(payload.get("boss_job_id") or "").strip(),
		}
		try:
			return self.store.save_job(
				job_key=job_key,
				jd_text=jd_text,
				rubric=normalize_rubric(rubric_payload),
				metadata=metadata,
			)
		except RecruiterAIError as exc:
			raise WebConsoleError("INVALID_JOB", str(exc)) from exc

	def list_jobs(self) -> list[dict[str, Any]]:
		return [self._job_summary(job) for job in self.store.list_jobs()]

	def get_job(self, job_key: str) -> dict[str, Any]:
		try:
			return self.store.get_job(job_key)
		except RecruiterAIError as exc:
			raise WebConsoleError("JOB_NOT_FOUND", str(exc), status=404) from exc

	def candidates(self, job_key: str, *, top: int = 200) -> dict[str, Any]:
		try:
			records = self.store.rank(job_key=job_key, top=max(1, min(top, 500)))
			return {
				"job_key": job_key,
				"items": summarize_ranking(records),
				"report": self.store.report(job_key=job_key, top=min(top, 50)),
			}
		except RecruiterAIError as exc:
			raise WebConsoleError("CANDIDATE_LIST_FAILED", str(exc)) from exc

	def candidate_detail(self, evaluation_id: str) -> dict[str, Any]:
		try:
			return self.store.get_evaluation(evaluation_id)
		except RecruiterAIError as exc:
			raise WebConsoleError("CANDIDATE_NOT_FOUND", str(exc), status=404) from exc

	def mark_candidate(self, evaluation_id: str, status: str, note: str = "") -> dict[str, Any]:
		try:
			return self.store.set_status(evaluation_id, status, note=note)
		except RecruiterAIError as exc:
			raise WebConsoleError("STATUS_UPDATE_FAILED", str(exc)) from exc

	def report(self, job_key: str, *, top: int = 10) -> dict[str, Any]:
		return self.store.report(job_key=job_key, top=max(1, min(top, 100)))

	def replies(self, *, evaluation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
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
			if len(items) >= limit:
				break
		return items

	def screen_local(
		self,
		payload: dict[str, Any],
		*,
		progress: ProgressCallback | None = None,
	) -> dict[str, Any]:
		job_key = str(payload.get("job_key") or "").strip()
		resumes = payload.get("resumes")
		force = bool(payload.get("force", False))
		if not job_key or not isinstance(resumes, list) or not resumes:
			raise WebConsoleError("INVALID_SCREEN_INPUT", "请选择岗位并上传至少一份 JSON 简历")
		job = self.get_job(job_key)
		jd_text = str(job.get("jd_text") or "")
		rubric = normalize_rubric(job.get("rubric") if isinstance(job.get("rubric"), dict) else None)
		service = self._service()
		processed: list[str] = []
		skipped: list[str] = []
		failed: list[dict[str, str]] = []
		total = len(resumes)
		for index, entry in enumerate(resumes, 1):
			name = f"resume-{index}.json"
			try:
				if not isinstance(entry, dict):
					raise RecruiterAIError("简历条目必须是对象")
				name = str(entry.get("name") or name)
				resume_payload = entry.get("payload")
				if not isinstance(resume_payload, dict):
					raise RecruiterAIError("简历 JSON 顶层必须是对象")
				resume = normalize_resume(resume_payload)
				source = {"type": "web-upload", "filename": name}
				if not force:
					existing = self.store.find_unchanged(
						job_key=job_key, resume=resume, source=source, rubric=rubric,
					)
					if existing is not None:
						skipped.append(str(existing.get("id", name)))
						continue
				evaluation = evaluate_resume(service, jd_text, resume, rubric)
				record = self.store.save_evaluation(
					job_key=job_key, jd_text=jd_text, resume=resume,
					evaluation=evaluation, source=source, rubric=rubric,
				)
				processed.append(str(record.get("id", name)))
			except (RecruiterAIError, AIServiceError, ValueError) as exc:
				failed.append({"file": name, "error": str(exc)})
			if progress:
				progress(int(index / total * 90), f"已处理 {index}/{total} 份简历")
		if progress:
			progress(100, "本地简历筛选完成")
		return {
			"job_key": job_key,
			"processed_count": len(processed),
			"skipped_unchanged_count": len(skipped),
			"failed_count": len(failed),
			"failed": failed,
			"ranking": summarize_ranking(self.store.rank(job_key=job_key, top=50)),
			"report": self.store.report(job_key=job_key, top=10),
			"messages_sent": 0,
		}

	def screen_boss(
		self,
		payload: dict[str, Any],
		*,
		progress: ProgressCallback | None = None,
	) -> dict[str, Any]:
		try:
			require_capability_mode(self.operating_mode(), "recruiter-applications")
			require_capability_mode(self.operating_mode(), "recruiter-resume")
		except ValueError as exc:
			raise WebConsoleError("COMPLIANCE_BLOCKED", str(exc), status=409) from exc
		job_key = str(payload.get("job_key") or "").strip()
		job_id = str(payload.get("job_id") or "").strip()
		pages = max(1, min(int(payload.get("pages", 1)), 10))
		limit = max(1, min(int(payload.get("limit", 30)), 100))
		force = bool(payload.get("force", False))
		include_chat = bool(payload.get("include_chat", False))
		draft_top = max(0, min(int(payload.get("draft_top", 0)), 20))
		if include_chat:
			try:
				require_capability_mode(self.operating_mode(), "recruiter-chatmsg")
			except ValueError as exc:
				raise WebConsoleError("COMPLIANCE_BLOCKED", str(exc), status=409) from exc
		if not job_key or not job_id:
			raise WebConsoleError("INVALID_SCREEN_INPUT", "请选择岗位并填写 BOSS 职位 ID")
		job = self.get_job(job_key)
		jd_text = str(job.get("jd_text") or "")
		rubric = normalize_rubric(job.get("rubric") if isinstance(job.get("rubric"), dict) else None)
		service = self._service()
		ctx = self._context()
		processed: list[str] = []
		skipped: list[str] = []
		failed: list[dict[str, str]] = []
		refs: list[dict[str, Any]] = []
		auth = self._auth()
		with get_recruiter_platform_instance(ctx, auth) as platform:
			for page in range(1, pages + 1):
				result = platform.friend_list(page=page, label_id=0, job_id=job_id)
				if not platform.is_success(result):
					code, message = platform.parse_error(result)
					raise WebConsoleError(str(code), message or "候选人投递列表获取失败", status=502)
				for item in candidate_items(platform.unwrap_data(result) or {}):
					refs.append(extract_candidate_ref(item, default_job_id=job_id))
					if len(refs) >= limit:
						break
				if progress:
					progress(min(20, int(page / pages * 20)), f"已读取第 {page}/{pages} 页候选人")
				if len(refs) >= limit:
					break
			for index, ref in enumerate(refs[:limit], 1):
				geek_id = str(ref.get("geek_id") or "")
				security_id = str(ref.get("security_id") or "")
				candidate_job_id = str(ref.get("job_id") or job_id)
				name = str(ref.get("name") or geek_id or f"candidate-{index}")
				if not geek_id or not security_id:
					failed.append({"candidate": name, "error": "缺少 geek_id 或 security_id"})
					continue
				result = platform.view_geek(geek_id, candidate_job_id, security_id=security_id)
				if not platform.is_success(result):
					code, message = platform.parse_error(result)
					failed.append({"candidate": name, "error": f"{code}: {message}"})
					continue
				try:
					resume = normalize_resume(parse_resume(result))
					source = {
						"type": "zhipin", "geek_id": geek_id,
						"security_id": security_id, "job_id": candidate_job_id,
						"friend_id": ref.get("friend_id"),
					}
					if not force:
						existing = self.store.find_unchanged(
							job_key=job_key, resume=resume, source=source, rubric=rubric,
						)
						if existing is not None:
							skipped.append(str(existing.get("id", geek_id)))
							continue
					evaluation = evaluate_resume(service, jd_text, resume, rubric)
					record = self.store.save_evaluation(
						job_key=job_key, jd_text=jd_text, resume=resume,
						evaluation=evaluation, source=source, rubric=rubric,
					)
					processed.append(str(record.get("id", geek_id)))
				except (RecruiterAIError, AIServiceError, ValueError) as exc:
					failed.append({"candidate": name, "error": str(exc)})
				if progress:
					progress(20 + int(index / max(1, len(refs)) * 65), f"已评估 {index}/{len(refs)} 位候选人")

			ranked = self.store.rank(job_key=job_key, top=max(50, draft_top))
			drafts: list[dict[str, Any]] = []
			for index, record in enumerate(ranked[:draft_top], 1):
				evaluation = record.get("evaluation")
				if not isinstance(evaluation, dict):
					continue
				conversation = ""
				source = record.get("source")
				if include_chat and isinstance(source, dict) and source.get("friend_id") not in (None, ""):
					chat_result = platform.chat_history(int(source["friend_id"]), count=30, max_msg_id=None)
					if platform.is_success(chat_result):
						conversation = conversation_to_text(platform.unwrap_data(chat_result) or {})
				intent = recommended_reply_intent(evaluation)
				draft = generate_reply_draft(service, jd_text, evaluation, conversation, intent)
				drafts.append(self.store.save_reply(
					evaluation_id=str(record.get("id", "")), intent=intent,
					conversation=conversation, draft=draft,
				))
				if progress:
					progress(85 + int(index / max(1, draft_top) * 14), f"已生成 {index}/{draft_top} 条回复草稿")
		if progress:
			progress(100, "BOSS 候选人筛选完成")
		return {
			"job_key": job_key,
			"job_id": job_id,
			"discovered_count": len(refs),
			"processed_count": len(processed),
			"skipped_unchanged_count": len(skipped),
			"failed_count": len(failed),
			"failed": failed,
			"ranking": summarize_ranking(self.store.rank(job_key=job_key, top=50)),
			"reply_drafts": drafts,
			"report": self.store.report(job_key=job_key, top=10),
			"messages_sent": 0,
			"human_review_required": True,
		}

	def generate_reply(self, payload: dict[str, Any]) -> dict[str, Any]:
		evaluation_id = str(payload.get("evaluation_id") or "").strip()
		conversation = str(payload.get("conversation") or "")
		intent = str(payload.get("intent") or "auto")
		if not evaluation_id:
			raise WebConsoleError("INVALID_REPLY_INPUT", "缺少候选人评估 ID")
		record = self.candidate_detail(evaluation_id)
		evaluation = record.get("evaluation")
		jd_text = record.get("jd_text")
		if not isinstance(evaluation, dict) or not isinstance(jd_text, str):
			raise WebConsoleError("INVALID_EVALUATION", "候选人评估记录不完整")
		try:
			draft = generate_reply_draft(self._service(), jd_text, evaluation, conversation, intent)
			return self.store.save_reply(
				evaluation_id=evaluation_id,
				intent=str(draft.get("intent") or intent),
				conversation=conversation,
				draft=draft,
			)
		except (RecruiterAIError, AIServiceError) as exc:
			raise WebConsoleError("REPLY_GENERATION_FAILED", str(exc), status=502) from exc
