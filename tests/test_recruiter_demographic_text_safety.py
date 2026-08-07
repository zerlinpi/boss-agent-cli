import json

from boss_agent_cli.recruiter_ai import build_evaluation_messages, redact_contact_text


def test_free_text_birth_dates_and_demographic_preferences_are_isolated() -> None:
	text = "出生于1995-05-06，男性优先，90后，年轻优先；5年 Java 经验，负责支付系统。"
	redacted = redact_contact_text(text)

	for secret in ("1995-05-06", "男性优先", "90后", "年轻优先"):
		assert secret not in redacted
	assert "5年 Java 经验" in redacted
	assert "支付系统" in redacted


def test_job_description_is_sanitized_before_evaluation_model_call() -> None:
	messages = build_evaluation_messages(
		"Java 后端，男性优先，30岁以下，5年 Java 经验",
		{"basic": {"name": "候选人A"}, "raw_text": "出生于1995年；负责订单系统"},
	)
	payload = json.loads(messages[1]["content"])

	job_description = payload["job_description"]
	resume_text = json.dumps(payload["resume"], ensure_ascii=False)
	assert "男性优先" not in job_description
	assert "30岁" not in job_description
	assert "5年 Java 经验" in job_description
	assert "1995年" not in resume_text
	assert "订单系统" in resume_text
