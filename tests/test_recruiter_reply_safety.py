from boss_agent_cli.web.reply_safety import scan_reply_safety


def test_reply_safety_detects_protected_attributes_and_promises():
	flags = scan_reply_safety("请说明婚育情况；通过后一定录用。")
	assert "protected_attribute" in flags
	assert "employment_promise" in flags


def test_reply_safety_detects_contact_exposure_and_length():
	flags = scan_reply_safety("请联系 13800000000 或 hr@example.com" + "a" * 1200)
	assert "contact_exposure" in flags
	assert "reply_too_long" in flags


def test_reply_safety_allows_neutral_follow_up():
	assert scan_reply_safety("你好，想进一步了解你在订单系统中负责的核心模块，可以简单介绍一下吗？") == []
