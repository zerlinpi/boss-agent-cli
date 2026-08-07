from boss_agent_cli.commands.recruiter.resume_parser import parse_resume


def _payload(base):
	return {"zpData": {"geekDetailInfo": {"geekBaseInfo": base}}}


def test_resume_parser_preserves_known_historical_gender_codes():
	assert parse_resume(_payload({"gender": 1}))["basic"]["gender"] == "男"
	assert parse_resume(_payload({"gender": 0}))["basic"]["gender"] == "女"


def test_resume_parser_prefers_explicit_gender_description():
	result = parse_resume(_payload({"gender": 99, "genderDesc": "未公开"}))
	assert result["basic"]["gender"] == "未公开"


def test_resume_parser_does_not_guess_unknown_or_missing_gender():
	assert parse_resume(_payload({"gender": 99}))["basic"]["gender"] == ""
	assert parse_resume(_payload({}))["basic"]["gender"] == ""


def test_resume_parser_tolerates_malformed_optional_lists():
	payload = {
		"zpData": {
			"geekDetailInfo": {
				"geekBaseInfo": None,
				"showExpectPosition": "unexpected",
				"geekWorkExpList": [None, {"company": "ACME"}],
				"geekProjExpList": ["unexpected"],
				"geekEduExpList": [None],
				"jobCompetitive": {"tips": [None, {"content": "沟通清晰"}]},
				"geekCertificationList": [None, {"certName": "PMP"}],
			}
		}
	}
	result = parse_resume(payload)
	assert result["basic"]["name"] == ""
	assert result["expectation"] == {"position": "", "salary": "", "city": ""}
	assert result["work_experience"][0]["company"] == "ACME"
	assert result["project_experience"] == []
	assert result["education"] == []
	assert result["competitive_analysis"] == ["沟通清晰"]
	assert result["certifications"] == ["PMP"]
