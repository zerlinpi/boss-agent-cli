from boss_agent_cli.web.export_security import safe_csv_cell


def test_safe_csv_cell_blocks_formula_prefixes_after_whitespace():
	for value in ("=1+1", "+SUM(A1:A2)", "-2+3", "@SUM(A1:A2)", "\t=cmd", "\r\n+cmd", "  @cmd"):
		assert safe_csv_cell(value).startswith("'")


def test_safe_csv_cell_keeps_normal_text_and_non_strings():
	assert safe_csv_cell("候选人A") == "候选人A"
	assert safe_csv_cell("  普通摘要") == "  普通摘要"
	assert safe_csv_cell(88) == 88
