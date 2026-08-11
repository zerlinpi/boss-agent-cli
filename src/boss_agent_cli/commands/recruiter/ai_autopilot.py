"""Recruiter AI autopilot: sync BOSS jobs and applications into the local review workflow.

The pipeline automates data collection, resume evaluation, ranking, and reply-draft
creation. It deliberately does not send messages or make final hire/reject decisions.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import click

from boss_agent_cli.ai.service import AIServiceError, ChatService
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.compliance import require_compliance_allowed
from boss_agent_cli.commands._recruiter_platform import get_recruiter_platform_instance
from boss_agent_cli.commands.recruiter.ai_common import (
	AIConfigurationError,
	draft_for_records,
	emit_ai_error,
	evaluate_local,
	platform_error,
	ranked_records_for_run,
	service_for,
)
from boss_agent_cli.commands.recruiter.resume_parser import parse_resume
from boss_agent_cli.display import handle_output
from boss_agent_cli.recruiter_ai import (
	RecruiterAIError,
	RecruiterAIStore,
	candidate_items,
	conversation_to_text,
	extract_candidate_ref,
	normalize_rubric,
	summarize_ranking,
)

_JOB_ID_FIELDS = ("encryptJobId", "encJobId", "jobId", "job_id", "encryptId")
_JOB_TITLE_FIELDS = ("jobName", "jobTitle", "title", "name")
_JOB_DESCRIPTION_FIELDS = (
	"jobDescription",
	"jobDesc",
	"description",
	"postDescription",
	"post_description",
	"content",
)


def _utc_now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
	if not isinstance(value, str) or not value.strip():
		return None
	text = value.strip()
	if text.endswith("Z"):
		text = f"{text[:-1]}+00:00"
	try:
		parsed = datetime.fromisoformat(text)
	except ValueError:
		return None
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


def _atomic_private_write(path: Path, payload: dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
	data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
	fd: int | None = None
	try:
		fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, "wb") as handle:
			fd = None
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, path)
		try:
			path.chmod(0o600)
		except OSError:
			pass
	finally:
		if fd is not None:
			os.close(fd)
		temporary.unlink(missing_ok=True)


class RecruiterAutopilotState:
	"""Small rebuildable sync ledger used to avoid unnecessary BOSS/API/model work."""

	def __init__(self, data_dir: Path) -> None:
		self.path = data_dir / "recruiter-ai" / "autopilot-state.json"
		self.payload = self._load()

	def _load(self) -> dict[str, Any]:
		default: dict[str, Any] = {"schema_version": 1, "candidates": {}, "last_run": None}
		if not self.path.is_file():
			return default
		try:
			loaded = json.loads(self.path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError, UnicodeDecodeError):
			# This file is only an optimization ledger. A corrupt copy is quarantined and
			# rebuilt; authoritative evaluations remain in RecruiterAIStore.
			try:
				self.path.replace(self.path.with_name(f"{self.path.name}.corrupt-{uuid4().hex[:8]}"))
			except OSError:
				pass
			return default
		if not isinstance(loaded, dict) or not isinstance(loaded.get("candidates", {}), dict):
			return default
		return cast("dict[str, Any]", loaded)

	def is_fresh(self, key: str, *, refresh_hours: int) -> bool:
		if refresh_hours <= 0:
			return False
		rows = self.payload.get("candidates")
		if not isinstance(rows, dict):
			return False
		row = rows.get(key)
		if not isinstance(row, dict) or not row.get("evaluation_id"):
			return False
		checked = _parse_timestamp(row.get("checked_at"))
		if checked is None:
			return False
		age_hours = (datetime.now(timezone.utc) - checked).total_seconds() / 3600
		return 0 <= age_hours < refresh_hours

	def record_success(self, key: str, *, evaluation_id: str, skipped_unchanged: bool) -> None:
		rows = self.payload.setdefault("candidates", {})
		if not isinstance(rows, dict):
			rows = {}
			self.payload["candidates"] = rows
		rows[key] = {
			"checked_at": _utc_now(),
			"evaluation_id": evaluation_id,
			"skipped_unchanged": bool(skipped_unchanged),
		}
		self.save()

	def finish_run(self, summary: dict[str, Any]) -> None:
		self.payload["last_run"] = {"finished_at": _utc_now(), "summary": summary}
		self.save()

	def save(self) -> None:
		_atomic_private_write(self.path, self.payload)


def _candidate_ref_key(job_key: str, ref: dict[str, Any]) -> str | None:
	for field in ("geek_id", "security_id", "friend_id"):
		value = ref.get(field)
		if value not in (None, ""):
			return f"{job_key}:{field}:{value}"
	return None


def _first_text(mapping: dict[str, Any], fields: tuple[str, ...]) -> str:
	for field in fields:
		value = mapping.get(field)
		if isinstance(value, str) and value.strip():
			return value.strip()
	return ""


def _walk_dicts(payload: Any) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	stack = [payload]
	seen: set[int] = set()
	while stack:
		item = stack.pop()
		identity = id(item)
		if identity in seen:
			continue
		seen.add(identity)
		if isinstance(item, dict):
			rows.append(item)
			stack.extend(item.values())
		elif isinstance(item, list):
			stack.extend(item)
	return rows


def extract_platform_jobs(payload: Any) -> list[dict[str, str]]:
	"""Best-effort normalize BOSS job-list payload without depending on one response nesting."""
	jobs: list[dict[str, str]] = []
	seen: set[str] = set()
	for row in _walk_dicts(payload):
		job_id = _first_text(row, _JOB_ID_FIELDS)
		if not job_id or job_id in seen:
			continue
		# Do not treat generic nested identifiers as jobs unless the same object looks job-like.
		title = _first_text(row, _JOB_TITLE_FIELDS)
		if not title and not any(field in row for field in ("jobStatus", "status", "jobName", "jobTitle")):
			continue
		seen.add(job_id)
		jobs.append({"job_id": job_id, "title": title})
	return jobs


def extract_job_description(payload: Any) -> str:
	"""Extract a usable JD from a job-detail response, preferring explicit description fields."""
	best = ""
	for row in _walk_dicts(payload):
		for field in _JOB_DESCRIPTION_FIELDS:
			value = row.get(field)
			if isinstance(value, str):
				text = value.strip()
				if len(text) > len(best):
					best = text
	return best


def _autopilot_job_key(job_id: str) -> str:
	return f"boss_{hashlib.sha256(job_id.encode('utf-8')).hexdigest()[:16]}"


def _configured_jobs(store: RecruiterAIStore) -> tuple[dict[str, dict[str, Any]], list[str]]:
	linked: dict[str, dict[str, Any]] = {}
	unlinked: list[str] = []
	for job in store.list_jobs():
		job_key = str(job.get("job_key") or "")
		metadata = job.get("metadata")
		boss_job_id = metadata.get("boss_job_id") if isinstance(metadata, dict) else None
		if boss_job_id not in (None, ""):
			linked[str(boss_job_id)] = job
		elif job_key:
			unlinked.append(job_key)
	return linked, unlinked


def _job_inputs(job: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
	job_key = str(job.get("job_key") or "").strip()
	jd_text = job.get("jd_text")
	rubric = job.get("rubric")
	if not job_key or not isinstance(jd_text, str) or not jd_text.strip() or not isinstance(rubric, dict):
		raise RecruiterAIError(f"岗位配置缺少 job_key/JD/rubric: {job_key or '<unknown>'}")
	return job_key, jd_text, normalize_rubric(rubric)


def _discover_and_configure_jobs(
	*,
	platform: Any,
	store: RecruiterAIStore,
	auto_configure: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
	"""Return current configured platform jobs, unconfigured platform jobs, and catalog warning."""
	linked, _ = _configured_jobs(store)
	response = platform.list_jobs()
	if not platform.is_success(response):
		# Keep existing mappings usable when BOSS job catalogue drifts, but make partial coverage explicit.
		return list(linked.values()), [], platform_error(platform, response, "BOSS 职位目录获取失败")
	platform_jobs = extract_platform_jobs(platform.unwrap_data(response) or {})
	if not platform_jobs:
		return list(linked.values()), [], "BOSS 职位目录返回成功，但未识别到职位 ID；已回退到本地已关联岗位"

	configured: list[dict[str, Any]] = []
	unconfigured: list[dict[str, str]] = []
	for item in platform_jobs:
		job_id = item["job_id"]
		existing = linked.get(job_id)
		if existing is not None:
			configured.append(existing)
			continue
		if not auto_configure:
			unconfigured.append(item)
			continue
		detail = platform.job_detail(job_id)
		if not platform.is_success(detail):
			unconfigured.append({**item, "error": platform_error(platform, detail, "职位详情读取失败")})
			continue
		jd_text = extract_job_description(platform.unwrap_data(detail) or {})
		if not jd_text:
			unconfigured.append({**item, "error": "职位详情中未识别到 JD 文本"})
			continue
		job_key = _autopilot_job_key(job_id)
		try:
			record = store.save_job(
				job_key=job_key,
				jd_text=jd_text,
				rubric=None,
				metadata={
					"boss_job_id": job_id,
					"boss_title": item.get("title", ""),
					"autopilot_discovered": True,
				},
			)
		except RecruiterAIError as exc:
			unconfigured.append({**item, "error": str(exc)})
			continue
		configured.append(record)
		linked[job_id] = record
	return configured, unconfigured, ""


def _collect_candidate_refs(
	*,
	platform: Any,
	job_id: str,
	max_pages: int,
	max_candidates: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
	refs: list[dict[str, Any]] = []
	failures: list[dict[str, str]] = []
	seen: set[str] = set()
	pages_read = 0
	for page in range(1, max_pages + 1):
		result = platform.friend_list(page=page, label_id=0, job_id=job_id)
		if not platform.is_success(result):
			failures.append({"page": str(page), "error": platform_error(platform, result, "候选人投递列表读取失败")})
			break
		pages_read = page
		items = candidate_items(platform.unwrap_data(result) or {})
		if not items:
			break
		new_on_page = 0
		for item in items:
			ref = extract_candidate_ref(item, default_job_id=job_id)
			identity = None
			for field in ("geek_id", "security_id", "friend_id"):
				if ref.get(field) not in (None, ""):
					identity = f"{field}:{ref[field]}"
					break
			if identity is not None and identity in seen:
				continue
			if identity is not None:
				seen.add(identity)
			refs.append(ref)
			new_on_page += 1
			if len(refs) >= max_candidates:
				return refs, failures, pages_read
		# Defensive stop for an endpoint that ignores page and repeats the same payload forever.
		if new_on_page == 0:
			break
	return refs, failures, pages_read


def _safe_score(record: dict[str, Any]) -> float | None:
	evaluation = record.get("evaluation")
	value = evaluation.get("total_score") if isinstance(evaluation, dict) else None
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return None
	number = float(value)
	return number if math.isfinite(number) else None


def run_autopilot(
	*,
	data_dir: Path,
	platform: Any,
	service: ChatService,
	store: RecruiterAIStore,
	max_pages: int,
	max_candidates_per_job: int,
	refresh_seen_hours: int,
	top: int,
	draft_top: int,
	include_chat: bool,
	force: bool,
	auto_configure: bool,
	selected_job_keys: set[str] | None,
) -> dict[str, Any]:
	state = RecruiterAutopilotState(data_dir)
	jobs, unconfigured_platform_jobs, catalog_warning = _discover_and_configure_jobs(
		platform=platform,
		store=store,
		auto_configure=auto_configure,
	)
	_, locally_unlinked = _configured_jobs(store)
	if selected_job_keys:
		jobs = [job for job in jobs if str(job.get("job_key") or "") in selected_job_keys]

	job_results: list[dict[str, Any]] = []
	totals = {
		"jobs_processed": 0,
		"candidates_discovered": 0,
		"candidates_fetched": 0,
		"evaluated": 0,
		"unchanged": 0,
		"freshness_skipped": 0,
		"failed": 0,
		"reply_drafts": 0,
	}

	for job in jobs:
		try:
			job_key, jd_text, rubric = _job_inputs(job)
		except RecruiterAIError as exc:
			job_results.append({"job_key": str(job.get("job_key") or ""), "error": str(exc)})
			totals["failed"] += 1
			continue
		metadata = job.get("metadata")
		job_id = str(metadata.get("boss_job_id") or "") if isinstance(metadata, dict) else ""
		if not job_id:
			continue

		refs, page_failures, pages_read = _collect_candidate_refs(
			platform=platform,
			job_id=job_id,
			max_pages=max_pages,
			max_candidates=max_candidates_per_job,
		)
		processed_ids: list[str] = []
		fetched = 0
		unchanged = 0
		freshness_skipped = 0
		candidate_failures: list[dict[str, str]] = list(page_failures)

		for ref in refs:
			ledger_key = _candidate_ref_key(job_key, ref)
			if ledger_key and not force and state.is_fresh(ledger_key, refresh_hours=refresh_seen_hours):
				freshness_skipped += 1
				continue
			geek_id = str(ref.get("geek_id") or "")
			security_id = str(ref.get("security_id") or "")
			candidate_job_id = str(ref.get("job_id") or job_id)
			if not geek_id or not security_id:
				candidate_failures.append({
					"candidate": str(ref.get("name") or ledger_key or "candidate"),
					"error": "候选人列表缺少 geek_id 或 security_id，无法读取简历",
				})
				continue
			result = platform.view_geek(geek_id, candidate_job_id, security_id=security_id)
			if not platform.is_success(result):
				candidate_failures.append({
					"candidate": str(ref.get("name") or geek_id),
					"error": platform_error(platform, result, "候选人简历获取失败"),
				})
				continue
			fetched += 1
			try:
				record = evaluate_local(
					service=service,
					store=store,
					jd_text=jd_text,
					rubric=rubric,
					resume_payload=parse_resume(result),
					job_key=job_key,
					source={
						"type": "zhipin",
						"geek_id": geek_id,
						"security_id": security_id,
						"job_id": candidate_job_id,
						"friend_id": ref.get("friend_id"),
					},
					save=True,
					force=force,
				)
			except AIConfigurationError:
				raise
			except (RecruiterAIError, AIServiceError) as exc:
				candidate_failures.append({"candidate": str(ref.get("name") or geek_id), "error": str(exc)})
				continue
			evaluation_id = str(record.get("id") or "")
			if record.get("skipped"):
				unchanged += 1
			else:
				processed_ids.append(evaluation_id)
			if ledger_key and evaluation_id:
				state.record_success(
					ledger_key,
					evaluation_id=evaluation_id,
					skipped_unchanged=bool(record.get("skipped")),
				)

		ranked_records, draft_records = ranked_records_for_run(
			store,
			job_key=job_key,
			top=top,
			draft_top=draft_top,
			processed_ids=processed_ids,
		)
		drafts: list[dict[str, Any]] = []
		draft_failures: list[dict[str, str]] = []
		if draft_top > 0 and draft_records:
			drafts, draft_failures = draft_for_records(
				service=service,
				store=store,
				platform=platform,
				records=draft_records,
				limit=draft_top,
				include_chat=include_chat,
				conversation_parser=conversation_to_text,
			)
		candidate_failures.extend(draft_failures)
		ranking = summarize_ranking(ranked_records[:top])
		scores = [score for record in ranked_records for score in [_safe_score(record)] if score is not None]
		job_result = {
			"job_key": job_key,
			"job_id": job_id,
			"title": metadata.get("boss_title", "") if isinstance(metadata, dict) else "",
			"pages_read": pages_read,
			"discovered_count": len(refs),
			"fetched_count": fetched,
			"evaluated_count": len(processed_ids),
			"unchanged_count": unchanged,
			"freshness_skipped_count": freshness_skipped,
			"failed_count": len(candidate_failures),
			"failures": candidate_failures,
			"reply_draft_count": len(drafts),
			"reply_drafts": drafts,
			"ranking": ranking,
			"score_summary": {
				"count": len(scores),
				"max": max(scores) if scores else None,
				"min": min(scores) if scores else None,
				"average": round(sum(scores) / len(scores), 2) if scores else None,
			},
			"human_review_required": True,
		}
		job_results.append(job_result)
		totals["jobs_processed"] += 1
		totals["candidates_discovered"] += len(refs)
		totals["candidates_fetched"] += fetched
		totals["evaluated"] += len(processed_ids)
		totals["unchanged"] += unchanged
		totals["freshness_skipped"] += freshness_skipped
		totals["failed"] += len(candidate_failures)
		totals["reply_drafts"] += len(drafts)

	summary = {
		"started_from": "boss-current-jobs",
		"finished_at": _utc_now(),
		"totals": totals,
		"jobs": job_results,
		"unconfigured_platform_jobs": unconfigured_platform_jobs,
		"locally_unlinked_job_keys": locally_unlinked,
		"catalog_warning": catalog_warning,
		"messages_sent": 0,
		"final_employment_decisions_automated": False,
		"human_review_required": True,
	}
	state.finish_run({"totals": totals, "catalog_warning": catalog_warning})
	return summary


@click.command("autopilot")
@click.option("--job-key", "job_keys", multiple=True, help="只处理指定本地 job_key；可重复传入。省略时处理所有当前已关联职位")
@click.option("--max-pages", default=30, type=click.IntRange(1, 100), show_default=True, help="每个职位最多读取的投递页数")
@click.option(
	"--max-candidates-per-job",
	default=2000,
	type=click.IntRange(1, 10000),
	show_default=True,
	help="单职位单轮候选人数安全上限",
)
@click.option(
	"--refresh-seen-hours",
	default=24,
	type=click.IntRange(0, 24 * 30),
	show_default=True,
	help="已处理候选人在该时间内不重复拉取；0 表示每轮都检查",
)
@click.option("--top", default=50, type=click.IntRange(1, 500), show_default=True, help="每个职位返回的排行榜数量")
@click.option("--draft-top", default=10, type=click.IntRange(0, 100), show_default=True, help="每个职位为本轮新评估的 Top N 生成回复草稿")
@click.option("--include-chat", is_flag=True, help="生成草稿时读取最近聊天上下文")
@click.option("--force", is_flag=True, help="忽略同步 freshness 和简历未变化检测，全部重新评估")
@click.option(
	"--auto-configure/--no-auto-configure",
	default=True,
	show_default=True,
	help="自动为 BOSS 当前但未关联的职位读取 JD 并建立本地评分配置",
)
@click.pass_context
def autopilot_cmd(
	ctx: click.Context,
	job_keys: tuple[str, ...],
	max_pages: int,
	max_candidates_per_job: int,
	refresh_seen_hours: int,
	top: int,
	draft_top: int,
	include_chat: bool,
	force: bool,
	auto_configure: bool,
) -> None:
	"""自动同步 BOSS 当前职位的全部投递并完成 AI 筛选、排名和回复草稿。"""
	if not require_compliance_allowed(ctx, "recruiter-applications"):
		return
	if not require_compliance_allowed(ctx, "recruiter-resume"):
		return
	if include_chat and not require_compliance_allowed(ctx, "recruiter-chatmsg"):
		return
	service = service_for(ctx, deferred=True)
	if service is None:
		return
	data_dir = ctx.obj["data_dir"]
	store = RecruiterAIStore(data_dir)
	auth = AuthManager(data_dir, logger=ctx.obj["logger"], platform=ctx.obj.get("platform", "zhipin"))
	try:
		with get_recruiter_platform_instance(ctx, auth) as platform:
			result = run_autopilot(
				data_dir=data_dir,
				platform=platform,
				service=service,
				store=store,
				max_pages=max_pages,
				max_candidates_per_job=max_candidates_per_job,
				refresh_seen_hours=refresh_seen_hours,
				top=top,
				draft_top=draft_top,
				include_chat=include_chat,
				force=force,
				auto_configure=auto_configure,
				selected_job_keys=set(job_keys) if job_keys else None,
			)
	except AIConfigurationError as exc:
		emit_ai_error(ctx, "recruiter-ai-autopilot", exc)
		return
	handle_output(
		ctx,
		"recruiter-ai-autopilot",
		result,
		hints={
			"next_actions": [
				"boss hr ai report --job-key <job_key> --top 20",
				"人工审核 reply_drafts 后回到 BOSS 官方页面发送",
				"再次运行 autopilot 只会增量处理新候选人/到期复查候选人",
			],
		},
	)
