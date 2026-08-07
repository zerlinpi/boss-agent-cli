import json

from boss_agent_cli.recruiter_ai import RecruiterAIStore, build_reply_messages, normalize_rubric, validate_evaluation


def _evaluation() -> dict[str, object]:
	return {
		"candidate_name": "张三",
		"total_score": 80,
		"recommendation": "interview",
		"confidence": 0.8,
		"hard_requirements": [],
		"dimensions": [],
		"strengths": ["张三有 Java 经验"],
		"concerns": [],
		"next_questions": [],
		"summary": "建议和张三沟通",
	}


def test_reply_prompt_redacts_candidate_identity_and_contact_details() -> None:
	messages = build_reply_messages(
		"Java 后端岗位",
		_evaluation(),
		"张三：手机号 13800000000，邮箱 zhangsan@example.com，微信 zhangsan88",
		"invite_interview",
	)
	payload = json.loads(messages[1]["content"])
	serialized = json.dumps(payload, ensure_ascii=False)

	assert "张三" not in serialized
	assert "13800000000" not in serialized
	assert "zhangsan@example.com" not in serialized
	assert "zhangsan88" not in serialized
	assert "candidate_name" not in payload["evaluation"]


def test_reply_store_persists_redacted_conversation(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	record = store.save_evaluation(
		job_key="java",
		jd_text="Java 后端岗位",
		resume={"basic": {"name": "张三"}},
		evaluation=validate_evaluation({
			"confidence": 0.8,
			"hard_requirements": [],
			"dimensions": [
				{
					"name": item["name"],
					"score": 0,
					"max_score": item["max_score"],
					"reason": "",
					"evidence": [],
				}
				for item in rubric["dimensions"]
			],
			"strengths": [],
			"concerns": [],
			"next_questions": [],
			"summary": "",
		}, rubric),
		rubric=rubric,
	)
	reply = store.save_reply(
		evaluation_id=record["id"],
		intent="invite_interview",
		conversation="张三 手机 13800000000 邮箱 zhangsan@example.com",
		draft={"reply": "你好，方便沟通吗？"},
	)

	assert "张三" not in reply["conversation"]
	assert "13800000000" not in reply["conversation"]
	assert "zhangsan@example.com" not in reply["conversation"]
