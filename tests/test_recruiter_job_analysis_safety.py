import json

from boss_agent_cli.web import RecruiterWebController


class FakeService:
	def __init__(self) -> None:
		self.messages = []

	def chat(self, messages, *, temperature=None, max_tokens=None):
		self.messages = messages
		return json.dumps({
			"title": "Java 后端工程师",
			"persona_summary": "有高并发后端经验的候选人",
			"hard_requirements": ["5年以上 Java 经验"],
			"dimensions": [
				{"name": "required_skills", "max_score": 100, "description": "Java 与分布式系统能力"},
			],
			"thresholds": {"strong_interview": 85, "interview": 70, "manual_review": 50},
			"suggested_questions": ["请介绍一次高并发系统优化经历"],
		}, ensure_ascii=False)


def test_job_analysis_sanitizes_model_input_without_mutating_local_jd(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	service = FakeService()
	controller._service = lambda: service  # type: ignore[method-assign]
	payload = {
		"jd_text": "Java 后端工程师，男性优先，90后，出生于1995年；要求5年以上 Java 经验。",
	}
	original = payload["jd_text"]

	result = controller.analyze_job(payload)

	assert payload["jd_text"] == original
	model_text = service.messages[1]["content"]
	for blocked in ("男性优先", "90后", "1995年"):
		assert blocked not in model_text
	assert "5年以上 Java 经验" in model_text
	assert result["rubric"]["dimensions"][0]["name"] == "required_skills"
