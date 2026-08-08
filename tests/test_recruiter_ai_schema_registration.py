from boss_agent_cli.commands import register, schema


def test_recruiter_ai_runtime_schema_lists_batch_workflow() -> None:
	register._register_recruiter_ai_schema()
	hr = schema.SCHEMA_DATA["commands"]["hr"]
	description = hr["subcommands"]["ai"]

	for command in (
		"configure",
		"jobs",
		"evaluate",
		"evaluate-geek",
		"screen",
		"screen-applications",
		"batch",
		"rank",
		"report",
		"mark",
		"reply",
	):
		assert command in description
