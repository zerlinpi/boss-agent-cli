from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web.reply_safety import scan_reply_safety


def test_reply_safety_detects_protected_attributes_and_promises():
	flags = scan_reply_safety("请说明婚育情况；通过后一定录用。")
	assert "protected_attribute" in flags
	assert "employment_promise" in flags


def test_reply_safety_detects_extended_protected_traits_and_offer_promises():
	flags = scan_reply_safety("请提供出生日期、党派和健康状况；你的 Offer 已确认。")
	assert "protected_attribute" in flags
	assert "employment_promise" in flags


def test_reply_safety_detects_contact_exposure_and_length():
	flags = scan_reply_safety("请联系 13800000000 或 hr@example.com" + "a" * 1200)
	assert "contact_exposure" in flags
	assert "reply_too_long" in flags


def test_reply_safety_detects_qq_and_landline():
	assert "contact_exposure" in scan_reply_safety("QQ：12345678")
	assert "contact_exposure" in scan_reply_safety("办公电话：010-12345678")


def test_reply_safety_allows_neutral_follow_up():
	assert scan_reply_safety("你好，想进一步了解你在订单系统中负责的核心模块，可以简单介绍一下吗？") == []


def test_store_applies_reply_safety_before_persistence(tmp_path):
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	evaluation = store.save_evaluation(
		job_key="java",
		jd_text="Java 后端工程师",
		resume={"basic": {"name": "候选人A"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		rubric=rubric,
	)
	record = store.save_reply(
		evaluation_id=evaluation["id"],
		intent="invite_interview",
		conversation="候选人原始聊天",
		draft={"reply": "请加 QQ：12345678，通过后一定录用。", "prohibited_content_detected": False},
	)
	draft = record["draft"]
	assert "contact_exposure" in draft["safety_flags"]
	assert "employment_promise" in draft["safety_flags"]
	assert draft["prohibited_content_detected"] is True
	assert record["requires_human_review"] is True
