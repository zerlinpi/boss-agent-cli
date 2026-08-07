import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, normalize_rubric


@pytest.mark.parametrize(
	"payload",
	[
		{"dimensions": [{"name": "age_match", "max_score": 100}]},
		{"dimensions": [{"name": "stability", "max_score": 100, "description": "已婚候选人更稳定"}]},
		{"dimensions": [{"name": "maritalStatus", "max_score": 100}]},
		{"hard_requirements": ["年龄 30 岁以下"]},
		{"hard_requirements": ["身体健康且无残障"]},
		{"instructions": "男性优先，党员加分"},
		{"instructions": "Prefer candidates by politicalAffiliation or religion"},
		{"title": "年轻男性销售经理"},
		{"persona_summary": "优先考虑未婚、无生育计划的候选人"},
		{"suggested_questions": ["你目前结婚了吗？", "介绍最近的 Java 项目"]},
	],
)
def test_normalize_rubric_rejects_protected_or_personal_criteria(payload) -> None:
	with pytest.raises(RecruiterAIError, match="不能使用"):
		normalize_rubric(payload)


def test_normalize_rubric_rejects_invalid_suggested_questions_shape() -> None:
	with pytest.raises(RecruiterAIError, match="suggested_questions 必须是列表"):
		normalize_rubric({"suggested_questions": "请介绍项目"})


def test_normalize_rubric_keeps_job_relevant_experience_and_technical_health_checks() -> None:
	rubric = normalize_rubric({
		"title": "Java 平台工程师",
		"dimensions": [
			{
				"name": "system_health_experience",
				"max_score": 50,
				"description": "Kubernetes health check、监控告警和可观测性经验",
			},
			{
				"name": "java_experience",
				"max_score": 50,
				"description": "Java 后端项目深度与可验证成果",
			},
		],
		"hard_requirements": ["5年以上 Java 经验", "具备当前岗位所需合法工作资格"],
		"instructions": "只根据技术能力、职责和项目证据评分",
		"persona_summary": "有平台工程经验、能承担复杂系统治理工作的候选人",
		"suggested_questions": ["请介绍一次 Kubernetes 故障排查经历"],
	})

	assert [item["name"] for item in rubric["dimensions"]] == [
		"system_health_experience",
		"java_experience",
	]
	assert rubric["hard_requirements"][0]["requirement"] == "5年以上 Java 经验"
