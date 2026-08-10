from boss_agent_cli.recruiter_ai import RecruiterAIStore, redact_contact_text, redact_resume_for_model
from boss_agent_cli.recruiter_ai_models import normalize_rubric


def test_generic_protected_criteria_are_removed_from_model_text() -> None:
	text = "年龄偏好不限；性别要求无；婚姻稳定优先；5年 Java 经验"
	redacted = redact_contact_text(text)
	assert "年龄偏好" not in redacted
	assert "性别要求" not in redacted
	assert "婚姻稳定优先" not in redacted
	assert "5年 Java 经验" in redacted


def test_generic_protected_criteria_consume_their_values_without_harming_business_context() -> None:
	text = "年龄限制 30 以下；性别偏好男性；负责男性用户增长；2019年启动支付项目"
	redacted = redact_contact_text(text)
	assert "年龄限制" not in redacted
	assert "30 以下" not in redacted
	assert "性别偏好" not in redacted
	assert "性别偏好男性" not in redacted
	assert "负责男性用户增长" in redacted
	assert "2019年启动支付项目" in redacted


def test_generic_protected_criteria_are_removed_from_nested_resume_text() -> None:
	payload = redact_resume_for_model({
		"raw_text": "年龄限制 30 以下，性别偏好男性，6年 Go 经验",
		"project": {"summary": "负责支付系统，婚姻稳定性不作为技术能力"},
	})
	text = str(payload)
	assert "年龄限制" not in text
	assert "30 以下" not in text
	assert "性别偏好" not in text
	assert "婚姻稳定性" not in text
	assert "6年 Go 经验" in text
	assert "支付系统" in text


def test_local_reply_storage_keeps_contacts_but_removes_identity_and_residential_data(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	record = store.save_evaluation(
		job_key="java",
		jd_text="Java 工程师",
		resume={"basic": {"name": "张三"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		rubric=normalize_rubric(),
	)
	conversation = (
		"电话 13800000000，微信 zhang_wechat；"
		"身份证号 110101199001011234；护照号 E12345678；"
		"家庭住址：北京市朝阳区某路88号；周三下午可以面试。"
	)
	reply = store.save_reply(
		evaluation_id=record["id"],
		intent="invite_interview",
		conversation=conversation,
		draft={"reply": "周三下午可以安排面试。"},
	)
	stored = reply["conversation"]
	assert "13800000000" in stored
	assert "zhang_wechat" in stored
	assert "110101199001011234" not in stored
	assert "E12345678" not in stored
	assert "北京市朝阳区某路88号" not in stored
	assert "周三下午可以面试" in stored
