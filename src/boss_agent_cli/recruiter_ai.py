"""Public compatibility surface for recruiter AI screening workflows."""

import boss_agent_cli.recruiter_ai_models as _model_module
from boss_agent_cli.recruiter_contact_retention import (
	RecruiterAIStore,
	extract_contact_details,
	install_model_sanitizer,
	normalize_resume,
	redact_text_for_model,
)
from boss_agent_cli.recruiter_identity_safety import install_identity_alias_sanitizer

# Install before recruiter_ai_evaluation imports model helpers by value.
install_model_sanitizer()
install_identity_alias_sanitizer()
redact_resume_for_model = _model_module.redact_resume_for_model

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

redact_contact_text = redact_text_for_model

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
