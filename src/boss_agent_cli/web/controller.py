"""Application services used by the local recruiter Web console."""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast

import click

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
	parse_ai_json,
	recommended_reply_intent,
	summarize_ranking,
)
from boss_agent_cli.web.audit import AuditLog
from boss_agent_cli.web.documents import DocumentParseError, SUPPORTED_EXTENSIONS, parse_uploaded_document

ProgressCallback = Callable[[int, str], None]

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _safe_identifier(value: str, *, label: str) -> str:
	value = value.strip()
	if not _SAFE_KEY.fullmatch(value):
		raise WebConsoleError("INVALID_IDENTIFIER", f"{label} 只能包含字母、数字、点、下划线和连字符")
	return value


def _csv_cell(value: Any) -> Any:
	if not isinstance(value, str):
		return value
	return "'" + value if value.startswith(("=", "+", "-", "@")) else value


class WebConsoleError(RuntimeError):
	"""Structured error surfaced by the Web API."""

	def __init__(self, code: str, message: str, *, status: int = 400):
		super().__init__(message)
		self.code = code
		self.status = status


class RecruiterWebController:
	"""Coordinate local persistence, AI calls, login, BOSS reads, and auditing."""

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
		self.audit = AuditLog(self.data_dir)
		self.config_path = self.data_dir / "config.json"

	def _config(self) -> dict[str, Any]:
		return load_config(self.config_path)

	def _write_config(self, payload: dict[str, Any]) -> None:
		temporary = self.config_path.with_suffix(".json.tmp")
		temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
		temporary.replace(self.config_path)

	def operating_mode(self) -> str:
		return str(self._config().get("operating_mode") or "assisted")

	def _context(self) -> click.Context:
		config = self._config()
		return click.Context(
			click.Command("recruiter-web"),
			obj={
				"data_dir": self.data_dir,
				"logger": self.logger,
				"platform": self.platform,
				"delay": tuple(config.get("request_delay", (1.5, 3.0))),
				"cdp_url": self.cdp_url or config.get("cdp_url"),
				"config": config,
				"role": "recruiter",
			},
		)

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
		auth = self.auth_status()
		onboarding = {
			"ai_configured": self.ai_store.is_configured(),
			"auth_ready": bool(auth["logged_in"]),
			"has_job": bool(jobs),
			"has_candidates": any(self.store.list_evaluations(job_key=str(job.get("job_key") or "")) for job in jobs),
		}
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
				"temperature": ai_config.get("ai_temperature", 0.2),
				"max_tokens": ai_config.get("ai_max_tokens", 4096),
				"providers": PROVIDER_BASE_URLS,
			},
			"auth": auth,
			"jobs": [self._job_summary(job) for job in jobs],
			"candidate_statuses": [
				status for status in ("new", "shortlisted", "interview", "hold", "hired", "rejected")
				if status in CANDIDATE_STATUSES
			],
			"supported_upload_extensions": list(SUPPORTED_EXTENSIONS),
			"onboarding": onboarding,
		}

	@staticmethod
	def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
		raw_metadata = job.get("metadata")
		metadata = cast("dict[str, Any]", raw_metadata) if isinstance(raw_metadata, dict) else {}
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
			self.audit.append("auth.login.failed", entity_type="auth", summary="BOSS 登录失败")
			raise WebConsoleError("LOGIN_FAILED", str(exc), status=502) from exc
		method = token.pop("_method", "unknown") if isinstance(token, dict) else "unknown"
		if progress:
			progress(100, "登录完成")
		self.audit.append(
			"auth.login.succeeded", entity_type="auth", summary=f"BOSS 登录成功（{method}）",
			metadata={"method": method},
		)
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
			ai_temperature=max(0.0, min(float(payload.get("temperature", 0.2)), 2.0)),
			ai_max_tokens=max(256, min(int(payload.get("max_tokens", 4096)), 32768)),
		)
		if api_key:
			self.ai_store.save_api_key(api_key)
		self.audit.append(
			"settings.ai.updated", entity_type="settings", entity_id="ai",
			summary=f"AI 服务已更新为 {provider} / {model}",
			metadata={"provider": provider, "model": model},
		)
		return self.bootstrap()["ai"]

	def set_operating_mode(self, mode: str) -> dict[str, Any]:
		if mode not in AVAILABLE_OPERATING_MODES:
			raise WebConsoleError("INVALID_MODE", f"不支持的运行模式: {mode}")
		config = self._config()
		config["operating_mode"] = mode
		config["low_risk_mode"] = mode != "research"
		self._write_config(config)
		self.audit.append(
			"settings.mode.updated", entity_type="settings", entity_id="operating_mode",
			summary=f"运行模式切换为 {mode}", metadata={"mode": mode},
		)
		return {"operating_mode": mode}

	def analyze_job(self, payload: dict[str, Any], *, progress: ProgressCallback | None = None) -> dict[str, Any]:
		jd_text = str(payload.get("jd_text") or "").strip()
		if len(jd_text) < 30:
			raise WebConsoleError("INVALID_JD", "请先填写完整岗位 JD")
		if progress:
			progress(10, "正在分析岗位职责和人才画像")
		messages = [
			{
				"role": "system",
				"content": (
					"你是资深招聘运营专家。根据 JD 生成可审计的招聘评分规则。"
					"不得包含年龄、性别、婚育、民族、健康等受保护属性。严格输出 JSON。"
				),
			},
			{
				"role": "user",
				"content": json.dumps({
					"job_description": jd_text,
					"output_schema": {
						"title": "岗位名称",
						"hard_requirements": [{"requirement": "string", "required": True}],
						"dimensions": [{"name": "string", "max_score": "integer"}],
						"thresholds": {"strong_interview": 85, "interview": 70, "manual_review": 55},
						"max_questions": 5,
						"persona_summary": "string",
						"suggested_questions": ["string"],
					},
				}, ensure_ascii=False),
			},
		]
		try:
			raw = self._service().chat(messages, temperature=0.1)
			result = parse_ai_json(raw)
			rubric = normalize_rubric(result)
		except (AIServiceError, RecruiterAIError, ValueError) as exc:
			raise WebConsoleError("JD_ANALYSIS_FAILED", str(exc), status=502) from exc
		if progress:
			progress(100, "岗位画像和评分规则已生成")
		self.audit.append("job.analyzed", entity_type="job", summary="AI 已生成岗位评分规则")
		return {
			"title": str(result.get("title") or "").strip(),
			"rubric": rubric,
			"persona_summary": str(result.get("persona_summary") or "").strip(),
			"suggested_questions": result.get("suggested_questions", []),
		}

	def save_job(self, payload: dict[str, Any]) -> dict[str, Any]:
		raw_job_key = str(payload.get("job_key") or "").strip()
		jd_text = str(payload.get("jd_text") or "").strip()
		if not raw_job_key or not jd_text:
			raise WebConsoleError("INVALID_JOB", "岗位标识和 JD 均不能为空")
		job_key = _safe_identifier(raw_job_key, label="岗位标识")
		rubric_payload = payload.get("rubric")
		if rubric_payload is not None and not isinstance(rubric_payload, dict):
			raise WebConsoleError("INVALID_RUBRIC", "评分规则必须是 JSON 对象")
		metadata = {
			"title": str(payload.get("title") or job_key).strip(),
			"boss_job_id": str(payload.get("boss_job_id") or "").strip(),
		}
		try:
			record = self.store.save_job(
				job_key=job_key,
				jd_text=jd_text,
				rubric=normalize_rubric(rubric_payload),
				metadata=metadata,
			)
		except RecruiterAIError as exc:
			raise WebConsoleError("INVALID_JOB", str(exc)) from exc
		self.audit.append(
			"job.saved", entity_type="job", entity_id=job_key,
			summary=f"岗位“{metadata['title']}”已保存", metadata={"boss_job_id": metadata["boss_job_id"]},
		)
		return record

	def list_jobs(self) -> list[dict[str, Any]]:
		return [self._job_summary(job) for job in self.store.list_jobs()]

	def get_job(self, job_key: str) -> dict[str, Any]:
		job_key = _safe_identifier(job_key, label="岗位标识")
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
				"analytics": self.analytics(job_key),
			}
		except RecruiterAIError as exc:
			raise WebConsoleError("CANDIDATE_LIST_FAILED", str(exc)) from exc

	def candidate_detail(self, evaluation_id: str) -> dict[str, Any]:
		evaluation_id = _safe_identifier(evaluation_id, label="候选人评估 ID")
		try:
			return self.store.get_evaluation(evaluation_id)
		except RecruiterAIError as exc:
			raise WebConsoleError("CANDIDATE_NOT_FOUND", str(exc), status=404) from exc

	def mark_candidate(self, evaluation_id: str, status: str, note: str = "") -> dict[str, Any]:
		evaluation_id = _safe_identifier(evaluation_id, label="候选人评估 ID")
		try:
			record = self.store.set_status(evaluation_id, status, note=note)
		except RecruiterAIError as exc:
			raise WebConsoleError("STATUS_UPDATE_FAILED", str(exc)) from exc
		self.audit.append(
			"candidate.status.updated", entity_type="candidate", entity_id=evaluation_id,
			summary=f"候选人状态更新为 {status}", metadata={"status": status, "note": note},
		)
		return record

	def bulk_mark_candidates(self, payload: dict[str, Any]) -> dict[str, Any]:
		ids = payload.get("evaluation_ids")
		status = str(payload.get("status") or "")
		note = str(payload.get("note") or "")
		if not isinstance(ids, list) or not ids:
			raise WebConsoleError("INVALID_BULK_INPUT", "请选择至少一位候选人")
		if status not in CANDIDATE_STATUSES:
			raise WebConsoleError("INVALID_BULK_INPUT", f"不支持的候选人状态: {status}")
		if len(ids) > 100:
			raise WebConsoleError("INVALID_BULK_INPUT", "单次最多操作 100 位候选人")
		updated: list[str] = []
		failed: list[dict[str, str]] = []
		for evaluation_id in ids:
			try:
				safe_id = _safe_identifier(str(evaluation_id), label="候选人评估 ID")
				self.store.set_status(safe_id, status, note=note)
				updated.append(safe_id)
			except RecruiterAIError as exc:
				failed.append({"evaluation_id": str(evaluation_id), "error": str(exc)})
		self.audit.append(
			"candidate.status.bulk_updated", entity_type="candidate", summary=f"批量更新 {len(updated)} 位候选人为 {status}",
			metadata={"status": status, "updated_count": len(updated), "failed_count": len(failed)},
		)
		return {"updated_ids": updated, "failed": failed, "status": status}

	def report(self, job_key: str, *, top: int = 10) -> dict[str, Any]:
		return self.store.report(job_key=job_key, top=max(1, min(top, 100)))

	def analytics(self, job_key: str) -> dict[str, Any]:
		records = list(self.store.latest_by_candidate(job_key=job_key).values())
		scores: list[float] = []
		confidences: list[float] = []
		recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
		recent = 0
		for record in records:
			evaluation = record.get("evaluation")
			if isinstance(evaluation, dict):
				score = evaluation.get("total_score")
				confidence = evaluation.get("confidence")
				if isinstance(score, (int, float)) and not isinstance(score, bool):
					scores.append(float(score))
				if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
					confidences.append(float(confidence))
			try:
				created = datetime.fromisoformat(str(record.get("created_at") or ""))
			except ValueError:
				continue
			if created >= recent_cutoff:
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

	def audit_events(self, *, limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
		return self.audit.list(limit=limit, action=action)

	def export_candidates(self, job_key: str) -> dict[str, str]:
		items = summarize_ranking(self.store.rank(job_key=job_key, top=500))
		buffer = io.StringIO()
		writer = csv.writer(buffer)
		writer.writerow(["rank", "candidate_name", "score", "recommendation", "status", "summary", "strengths", "concerns"])
		for item in items:
			writer.writerow([
				item.get("rank"), _csv_cell(item.get("candidate_name")), item.get("total_score"),
				item.get("recommendation"), item.get("status"), _csv_cell(item.get("summary")),
				_csv_cell(" | ".join(item.get("strengths") or [])),
				_csv_cell(" | ".join(item.get("concerns") or [])),
			])
		return {"filename": f"{job_key}-candidates.csv", "content": "\ufeff" + buffer.getvalue()}

	def screen_local(
		self,
		payload: dict[str, Any],
		*,
		progress: ProgressCallback | None = None,
	) -> dict[str, Any]:
		job_key = _safe_identifier(str(payload.get("job_key") or ""), label="岗位标识")
		entries = payload.get("documents", payload.get("resumes"))
		force = bool(payload.get("force", False))
		if not job_key or not isinstance(entries, list) or not entries:
			raise WebConsoleError("INVALID_SCREEN_INPUT", "请选择岗位并上传至少一份简历")
		if len(entries) > 100:
			raise WebConsoleError("INVALID_SCREEN_INPUT", "单次最多上传 100 份简历")
		job = self.get_job(job_key)
		jd_text = str(job.get("jd_text") or "")
		raw_rubric = job.get("rubric")
		rubric = normalize_rubric(cast("dict[str, Any]", raw_rubric) if isinstance(raw_rubric, dict) else None)
		service = self._service()
		processed: list[str] = []
		skipped: list[str] = []
		failed: list[dict[str, str]] = []
		total = len(entries)
		for index, entry in enumerate(entries, 1):
			name = f"resume-{index}"
			try:
				if not isinstance(entry, dict):
					raise DocumentParseError("简历条目必须是对象")
				name = str(entry.get("name") or name)
				resume_payload, source = parse_uploaded_document(entry)
				resume = normalize_resume(resume_payload)
				if not force:
					existing = self.store.find_unchanged(job_key=job_key, resume=resume, source=source, rubric=rubric)
					if existing is not None:
						skipped.append(str(existing.get("id", name)))
						continue
				evaluation = evaluate_resume(service, jd_text, resume, rubric)
				record = self.store.save_evaluation(
					job_key=job_key, jd_text=jd_text, resume=resume,
					evaluation=evaluation, source=source, rubric=rubric,
				)
				processed.append(str(record.get("id", name)))
			except (DocumentParseError, RecruiterAIError, AIServiceError, ValueError) as exc:
				failed.append({"file": name, "error": str(exc)})
			if progress:
				progress(int(index / total * 90), f"已处理 {index}/{total} 份简历")
		if progress:
			progress(100, "本地简历筛选完成")
		self.audit.append(
			"screen.local.completed", entity_type="screening", entity_id=job_key,
			summary=f"完成本地筛选：{len(processed)} 成功，{len(failed)} 失败",
			metadata={"processed": len(processed), "skipped": len(skipped), "failed": len(failed)},
		)
		return {
			"job_key": job_key,
			"discovered_count": total,
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
		job_key = _safe_identifier(str(payload.get("job_key") or ""), label="岗位标识")
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
		raw_rubric = job.get("rubric")
		rubric = normalize_rubric(cast("dict[str, Any]", raw_rubric) if isinstance(raw_rubric, dict) else None)
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
						existing = self.store.find_unchanged(job_key=job_key, resume=resume, source=source, rubric=rubric)
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
			draft_failures: list[dict[str, str]] = []
			for index, record in enumerate(ranked[:draft_top], 1):
				evaluation = record.get("evaluation")
				if not isinstance(evaluation, dict):
					continue
				conversation = ""
				raw_source = record.get("source")
				source = cast("dict[str, Any]", raw_source) if isinstance(raw_source, dict) else {}
				friend_id = source.get("friend_id")
				if (
					include_chat
					and not isinstance(friend_id, bool)
					and isinstance(friend_id, (int, str))
					and str(friend_id).strip()
				):
					chat_result = platform.chat_history(int(friend_id), count=30, max_msg_id=None)
					if platform.is_success(chat_result):
						conversation = conversation_to_text(platform.unwrap_data(chat_result) or {})
				try:
					intent = recommended_reply_intent(evaluation)
					draft = generate_reply_draft(service, jd_text, evaluation, conversation, intent)
					drafts.append(self.store.save_reply(
						evaluation_id=str(record.get("id", "")), intent=intent,
						conversation=conversation, draft=draft,
					))
				except (RecruiterAIError, AIServiceError, ValueError) as exc:
					draft_failures.append({"evaluation_id": str(record.get("id", "")), "error": str(exc)})
				if progress:
					progress(85 + int(index / max(1, draft_top) * 14), f"已生成 {index}/{draft_top} 条回复草稿")
		if progress:
			progress(100, "BOSS 候选人筛选完成")
		self.audit.append(
			"screen.boss.completed", entity_type="screening", entity_id=job_key,
			summary=f"完成 BOSS 筛选：发现 {len(refs)}，成功 {len(processed)}",
			metadata={"job_id": job_id, "processed": len(processed), "skipped": len(skipped), "failed": len(failed)},
		)
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
			"reply_draft_failures": draft_failures,
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
			reply = self.store.save_reply(
				evaluation_id=evaluation_id,
				intent=str(draft.get("intent") or intent),
				conversation=conversation,
				draft=draft,
			)
		except (RecruiterAIError, AIServiceError) as exc:
			raise WebConsoleError("REPLY_GENERATION_FAILED", str(exc), status=502) from exc
		self.audit.append(
			"reply.generated", entity_type="candidate", entity_id=evaluation_id,
			summary="已生成待人工审核的回复草稿", metadata={"intent": reply.get("intent")},
		)
		return reply
