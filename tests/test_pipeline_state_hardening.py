from boss_agent_cli.pipeline_state import build_pipeline_items


def test_pipeline_coerces_numeric_string_fields() -> None:
	items = build_pipeline_items(
		chat_items=[{
			"securityId": 123,
			"encryptJobId": 456,
			"relationType": "1",
			"unreadMsgCount": "2",
			"lastTS": "1700000000000",
			"brandName": 789,
			"title": 101,
			"lastMsg": 202,
		}],
		interview_items=[],
		now_ts_ms=1700000000000,
		stale_days=3,
	)

	assert items[0]["stage"] == "reply_needed"
	assert items[0]["unread"] == 2
	assert items[0]["security_id"] == "123"
	assert items[0]["company"] == "789"


def test_pipeline_ignores_invalid_numeric_fields_without_crashing() -> None:
	items = build_pipeline_items(
		chat_items=[{
			"relationType": {"bad": 1},
			"unreadMsgCount": [1],
			"lastTS": "not-a-timestamp",
			"brandName": "Company",
			"title": "Role",
		}],
		interview_items=["bad", {"brandName": "Company", "jobName": "Role"}],
		now_ts_ms=1700000000000,
		stale_days=3,
	)

	assert {item["source"] for item in items} == {"chat", "interview"}
	chat = next(item for item in items if item["source"] == "chat")
	assert chat["stage"] == "chatting"
	assert chat["last_time"] == "-"


def test_pipeline_does_not_treat_future_timestamp_as_stale() -> None:
	items = build_pipeline_items(
		chat_items=[{"lastTS": 2000, "brandName": "Company", "title": "Role"}],
		interview_items=[],
		now_ts_ms=1000,
		stale_days=0,
	)
	assert items[0]["stage"] == "chatting"
