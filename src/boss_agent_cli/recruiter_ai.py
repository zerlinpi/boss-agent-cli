"""Public compatibility surface for recruiter AI screening workflows."""

from typing import Any

import boss_agent_cli.recruiter_ai_models as _model_module
import boss_agent_cli.recruiter_ai_store as _store_module
from boss_agent_cli.recruiter_contact_retention import (
	RecruiterAIStore,
	extract_contact_details,
	install_model_sanitizer,
	normalize_resume as _base_normalize_resume,
)
from boss_agent_cli.recruiter_candidate_identity import install_stable_local_candidate_identity
from boss_agent_cli.recruiter_candidate_state import install_candidate_state_retention
from boss_agent_cli.recruiter_candidate_versioning import install_candidate_version_ordering
from boss_agent_cli.recruiter_identity_safety import install_identity_alias_sanitizer
from boss_agent_cli.recruiter_job_cache import install_job_profile_cache
from boss_agent_cli.recruiter_local_data_safety import install_local_data_safety, sanitize_local_resume
from boss_agent_cli.recruiter_privacy_hardening import (
	install_evaluation_output_hardening,
	install_model_and_store_hardening,
)

# Install before recruiter_ai_evaluation imports model helpers by value.
install_model_sanitizer()
install_identity_alias_sanitizer()
install_stable_local_candidate_identity()
install_candidate_state_retention()
install_candidate_version_ordering(RecruiterAIStore)
install_model_and_store_hardening(_model_module, RecruiterAIStore)
install_local_data_safety(_model_module, RecruiterAIStore)
# recruiter_ai_store imports this helper by value before the runtime hardening layer is installed.
# Keep direct Store API calls on the same rubric contract as CLI/Web entry points.
_store_module.normalize_rubric = _model_module.normalize_rubric
install_job_profile_cache(RecruiterAIStore)
redact_resume_for_model = _model_module.redact_resume_for_model


def normalize_resume(payload: dict[str, Any]) -> dict[str, Any]:
	"""Normalize a resume and enforce the local high-risk identity-data policy."""
	return sanitize_local_resume(_base_normalize_resume(payload))


import boss_agent_cli.recruiter_ai_evaluation as _evaluation_module  # noqa: E402

install_evaluation_output_hardening(_evaluation_module, _model_module)

from boss_agent_cli.recruiter_ai_evaluation import (  # noqa: E402
	build_evaluation_messages,
	build_reply_messages,
	evaluate_resume,
	generate_reply_draft,
	recommended_reply_intent,
	validate_evaluation,
)
from boss_agent_cli.recruiter_ai_models import (  # noqa: E402
	CANDIDATE_STATUSES,
	CONTACT_FIELDS,
	DEFAULT_DIMENSIONS,
	DEFAULT_THRESHOLDS,
	PROTECTED_BASIC_FIELDS,
	RECOMMENDATIONS,
	SCHEMA_VERSION,
	RecruiterAIError,
	candidate_items,
	candidate_key,
	candidate_name,
	conversation_to_text,
	extract_candidate_ref,
	normalize_rubric,
	parse_ai_json,
	read_json_input,
	read_text_input,
	resume_fingerprint,
	rubric_fingerprint,
)
from boss_agent_cli.recruiter_ai_store import summarize_ranking  # noqa: E402

redact_contact_text = _model_module.redact_contact_text

__all__ = [
	"CANDIDATE_STATUSES",
	"CONTACT_FIELDS",
	"DEFAULT_DIMENSIONS",
	"DEFAULT_THRESHOLDS",
	"PROTECTED_BASIC_FIELDS",
	"RECOMMENDATIONS",
	"SCHEMA_VERSION",
	"RecruiterAIError",
	"RecruiterAIStore",
	"build_evaluation_messages",
	"build_reply_messages",
	"candidate_items",
	"candidate_key",
	"candidate_name",
	"conversation_to_text",
	"evaluate_resume",
	"extract_candidate_ref",
	"extract_contact_details",
	"generate_reply_draft",
	"normalize_resume",
	"normalize_rubric",
	"parse_ai_json",
	"read_json_input",
	"read_text_input",
	"recommended_reply_intent",
	"redact_contact_text",
	"redact_resume_for_model",
	"resume_fingerprint",
	"rubric_fingerprint",
	"summarize_ranking",
	"validate_evaluation",
]