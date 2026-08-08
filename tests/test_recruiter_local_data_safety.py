import json

from boss_agent_cli.recruiter_ai import (
	RecruiterAIStore,
	normalize_resume,
	normalize_rubric,
	redact_contact_text,
	redact_resume_for_model,
)
from boss_agent_cli.web.reply_safety import scan_reply_safety


def test_normalize_resume_removes_formatted_id_passport_and_residential_address() -> None:
	resume = normalize_resume({
		"basic": {"name": "A"},
		"passportNo": "E12345678",
		"raw_text": (
			"身份证 110101 19900101 1234；护照号 E12345678；"
			"家庭住址 上海市浦东新区世纪大道100号；电话 13800000000；5年 Java 经验"
		),
	})
	payload = json.dumps(resume, ensure_ascii=False)

	assert "passportNo" not in resume
	assert "110101 19900101 1234" not in payload
	assert "E12345678" not in payload
	assert "世纪大道100号" not in payload
	assert "13800000000" in payload
	assert "5年 Java 经验" in payload


def test_direct_store_save_evaluation_applies_same_local_safety_policy(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	record = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={
			"basic": {"name": "A"},
			"passport": "E12345678",
			"raw_text": "身份证 110101-19900101-1234；现住址：北京市朝阳区某路88号；微信 abc_12345",
		},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		rubric=rubric,
	)
	payload = json.dumps(record["resume"], ensure_ascii=False)
	assert "passport" not in record["resume"]
	assert "110101-19900101-1234" not in payload
	assert "某路88号" not in payload
	assert "abc_12345" in payload


def test_model_text_and_resume_redaction_cover_formatted_identity_data() -> None:
	text = "身份证 110101 19900101 1234，护照号 E12345678，家庭住址 上海市浦东新区世纪大道100号，5年 Go 经验"
	redacted = redact_contact_text(text)
	assert "110101 19900101 1234" not in redacted
	assert "E12345678" not in redacted
	assert "世纪大道100号" not in redacted
	assert "5年 Go 经验" in redacted

	resume_payload = json.dumps(redact_resume_for_model({"raw_text": text}), ensure_ascii=False)
	assert "110101 19900101 1234" not in resume_payload
	assert "E12345678" not in resume_payload
	assert "世纪大道100号" not in resume_payload


def test_reply_safety_uses_same_formatted_identity_detection() -> None:
	assert "identity_exposure" in scan_reply_safety("身份证 110101 19900101 1234")
	assert "identity_exposure" in scan_reply_safety("家庭住址 上海市浦东新区世纪大道100号")
	assert "identity_exposure" not in scan_reply_safety("面试地址 上海市徐汇区公司会议室")
