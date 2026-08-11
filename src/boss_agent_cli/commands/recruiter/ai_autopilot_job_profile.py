"""Automatic JD refresh and AI job-profile generation for recruiter autopilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boss_agent_cli.ai.service import AIServiceError, ChatService
from boss_agent_cli.commands.recruiter import ai_autopilot as autopilot_module
from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore, normalize_rubric, parse_ai_json

_CORE_RUN_AUTOPILOT = autopilot_module.run_autopilot


def _profile_job(service: ChatService, jd_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
	messages = [
		{
			"role": "system",
			"content": (
				"你是资深招聘运营专家。根据 JD 生成可审计的招聘评分规则。"
				"不得使用年龄、性别、婚育、民族/种族、宗教、健康/残障、政治身份等受保护属性，"
				"不得使用这些属性的代理条件。严格输出 JSON。"
			),
		},
		{
			"role": "user",
			"content": json.dumps(
				{
					"job_description": jd_text,
					"output_schema": {
						"title": "岗位名称",
						"hard_requirements": [{"requirement": "string", "required": True}],
						"dimensions": [{"name": "string", "max_score": "positive integer"}],
						"thresholds": {
							"strong_interview": 85,
							"interview": 70,
							"manual_review": 55,
						},
						"max_questions": 5,
						"persona_summary": "string",
						"suggested_questions": ["string"],
					},
				},
				ensure_ascii=False,
			),
		},
	]
	raw = service.chat(messages, temperature=0.1)
	payload = parse_ai_json(raw)
	# normalize_rubric performs the existing local hard validation, including protected-trait rejection.
	rubric = normalize_rubric(payload)
	return payload, rubric


def prepare_autopilot_job_profiles(
	*,
	platform: Any,
	store: RecruiterAIStore,
	service: ChatService,
	auto_configure: bool,
) -> dict[str, Any]:
	"""Discover missing jobs, refresh auto-managed JDs, and generate a tailored safe rubric when needed."""
	if not auto_configure:
		return {"updated": [], "warnings": [], "catalog_warning": "", "unconfigured_platform_jobs": []}

	jobs, unconfigured, catalog_warning = autopilot_module._discover_and_configure_jobs(
		platform=platform,
		store=store,
		auto_configure=True,
	)
	updated: list[dict[str, str]] = []
	warnings: list[dict[str, str]] = []

	for job in jobs:
		metadata = job.get("metadata")
		if not isinstance(metadata, dict) or not metadata.get("autopilot_discovered"):
			continue
		job_key = str(job.get("job_key") or "").strip()
		job_id = str(metadata.get("boss_job_id") or "").strip()
		if not job_key or not job_id:
			continue

		latest_jd = str(job.get("jd_text") or "").strip()
		detail = platform.job_detail(job_id)
		if platform.is_success(detail):
			detail_jd = autopilot_module.extract_job_description(platform.unwrap_data(detail) or {})
			if detail_jd:
				latest_jd = detail_jd
		else:
			warnings.append({
				"job_key": job_key,
				"job_id": job_id,
				"warning": autopilot_module.platform_error(platform, detail, "职位 JD 刷新失败，继续使用本地版本"),
			})

		jd_changed = latest_jd != str(job.get("jd_text") or "").strip()
		profile_generated = bool(metadata.get("autopilot_profile_generated"))
		if not jd_changed and profile_generated:
			continue

		try:
			profile, rubric = _profile_job(service, latest_jd)
		except (AIServiceError, RecruiterAIError, ValueError) as exc:
			warnings.append({
				"job_key": job_key,
				"job_id": job_id,
				"warning": f"AI 岗位画像生成失败，继续使用现有安全评分规则: {exc}",
			})
			# If the platform JD changed but profiling failed, do not save the new JD with an old rubric;
			# the next run will retry the profile generation instead of falsely marking it current.
			continue

		updated_metadata = dict(metadata)
		updated_metadata.update({
			"title": str(profile.get("title") or metadata.get("boss_title") or job_key).strip(),
			"boss_title": str(metadata.get("boss_title") or profile.get("title") or "").strip(),
			"autopilot_profile_generated": True,
			"autopilot_persona_summary": str(profile.get("persona_summary") or "").strip(),
			"autopilot_suggested_questions": profile.get("suggested_questions", []),
		})
		store.save_job(
			job_key=job_key,
			jd_text=latest_jd,
			rubric=rubric,
			metadata=updated_metadata,
		)
		updated.append({
			"job_key": job_key,
			"job_id": job_id,
			"reason": "jd_changed" if jd_changed else "initial_ai_profile",
		})

	return {
		"updated": updated,
		"warnings": warnings,
		"catalog_warning": catalog_warning,
		"unconfigured_platform_jobs": unconfigured,
	}


def run_profiled_autopilot(
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
	"""Prepare current job profiles, then execute the normal incremental candidate pipeline."""
	# Explicit --job-key is a scoped validation/operation mode. Do not discover/profile unrelated
	# BOSS jobs as a side effect; selected keys must already exist locally and remain the only scope.
	profile_auto_configure = auto_configure and selected_job_keys is None
	profile_sync = prepare_autopilot_job_profiles(
		platform=platform,
		store=store,
		service=service,
		auto_configure=profile_auto_configure,
	)
	if auto_configure and selected_job_keys is not None:
		profile_sync["selection_scope"] = "explicit_job_keys_no_auto_discovery"
	result = _CORE_RUN_AUTOPILOT(
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
		# Discovery already ran above for all-job mode. Explicit job selection must not expand scope.
		auto_configure=False,
		selected_job_keys=selected_job_keys,
	)
	result["job_profile_sync"] = profile_sync
	if profile_sync["unconfigured_platform_jobs"]:
		result["unconfigured_platform_jobs"] = profile_sync["unconfigured_platform_jobs"]
	if not result.get("catalog_warning") and profile_sync["catalog_warning"]:
		result["catalog_warning"] = profile_sync["catalog_warning"]
	return result
