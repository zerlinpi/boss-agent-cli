import json

from boss_agent_cli.recruiter_ai import (
	RecruiterAIStore,
	build_reply_messages,
	extract_contact_details,
	normalize_resume,
	normalize_rubric,
	redact_resume_for_model,
)


def test_local_resume_keeps_recruiter_useful_fields_and_contacts_but_drops_identity_numbers():
	resume = normalize_resume({
		"basic": {"name": "张三", "age": "31", "gender": "男", "marital_status": "已婚"},
		"contact": {
			"phone": "13800000000",
			"email": "zhang@example.com",
			"wechat": "zhang_wechat",
			"qq": "12345678",
			"id_number": "110101199001011234",
		},
		"raw_text": "张三，婚姻状况：已婚，年龄：31，电话 13800000000，微信：zhang_wechat，身份证 110101199001011234",
	})

	assert resume["basic"] == {"name": "张三", "age": "31", "gender": "男", "marital_status": "已婚"}
	assert resume["contact"]["phone"] == "13800000000"
	assert resume["contact"]["email"] == "zhang@example.com"
	assert "id_number" not in resume["contact"]
	assert "110101199001011234" not in resume["raw_text"]
	assert "已婚" in resume["raw_text"]

	contacts = extract_contact_details(resume)
	assert contacts["phone"] == ["13800000000"]
	assert contacts["email"] == ["zhang@example.com"]
	assert "zhang_wechat" in contacts["wechat"]
	assert "12345678" in contacts["qq"]


def test_model_payload_excludes_identity_contacts_and_protected_text():
	resume = normalize_resume({
		"basic": {"name": "张三"},
		"contact": {"phone": "13800000000", "email": "zhang@example.com"},
		"raw_text": "张三，婚姻状况：已婚，年龄：31，性别：男，手机 13800000000",
	})

	payload = json.dumps(redact_resume_for_model(resume), ensure_ascii=False)
	assert "张三" not in payload
	assert "13800000000" not in payload
	assert "zhang@example.com" not in payload
	assert "已婚" not in payload
	assert "年龄：31" not in payload
	assert "性别：男" not in payload


def test_model_payload_sanitizes_compact_resume_demographics():
	resume = normalize_resume({
		"name": "李四",
		"raw_text": "李四 | 31岁 | 男 | 已婚 | 5年 Java 经验 | 微信：lisi_2026",
	})
	payload = json.dumps(redact_resume_for_model(resume), ensure_ascii=False)
	assert "李四" not in payload
	assert "31岁" not in payload
	assert "已婚" not in payload
	assert "lisi_2026" not in payload
	assert "[年龄已隔离]" in payload
	assert "[性别已隔离]" in payload
	assert "[婚姻状况已隔离]" in payload
	assert "5年 Java 经验" in payload


def test_model_payload_handles_camel_case_chinese_aliases_landline_and_name_in_text():
	resume = normalize_resume({
		"candidateName": "王五",
		"maritalStatus": "已婚",
		"birthDate": "1992-05-06",
		"sex": "男",
		"healthStatus": "良好",
		"phoneNumber": "010-12345678",
		"联系方式": {"微信": "wangwu_2026", "邮箱": "wangwu@example.com"},
		"raw_text": "王五，健康状况：良好；宗教：无；电话 010-12345678；5年 Python 经验",
	})

	# Human-facing local data remains available except high-risk identity/address fields.
	assert resume["maritalStatus"] == "已婚"
	assert resume["phoneNumber"] == "010-12345678"
	assert "王五" in resume["raw_text"]
	contacts = extract_contact_details(resume)
	assert "010-12345678" in contacts["phone"]
	assert "wangwu_2026" in contacts["wechat"]

	payload = json.dumps(redact_resume_for_model(resume), ensure_ascii=False)
	for secret in (
		"王五", "已婚", "1992-05-06", "良好", "010-12345678", "wangwu_2026", "wangwu@example.com",
	):
		assert secret not in payload
	assert "5年 Python 经验" in payload
	assert "[姓名已脱敏]" in payload


def test_reply_model_context_is_sanitized_but_store_keeps_local_conversation(tmp_path):
	evaluation = {"candidate_name": "张三", "recommendation": "interview", "next_questions": []}
	messages = build_reply_messages(
		"Java 工程师",
		evaluation,
		"张三：我已婚，微信：zhang_wechat，电话 13800000000",
		"invite_interview",
	)
	model_input = messages[1]["content"]
	assert "张三" not in model_input
	assert "已婚" not in model_input
	assert "zhang_wechat" not in model_input
	assert "13800000000" not in model_input

	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	record = store.save_evaluation(
		job_key="java",
		jd_text="Java 工程师",
		resume={"basic": {"name": "张三"}, "phone": "13800000000", "wechat": "zhang_wechat"},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		rubric=rubric,
	)
	assert record["contacts"]["phone"] == ["13800000000"]
	reply = store.save_reply(
		evaluation_id=record["id"],
		intent="invite_interview",
		conversation="微信：zhang_wechat，电话 13800000000",
		draft={"reply": "方便约个时间面试吗？"},
	)
	assert "13800000000" in reply["conversation"]
	assert reply["local_contact_retained"] is True
