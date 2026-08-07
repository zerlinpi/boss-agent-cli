from boss_agent_cli.recruiter_ai import extract_candidate_ref
from boss_agent_cli.web.reliability import _dedupe_candidate_items


def test_candidate_page_dedup_uses_platform_identity_not_display_name():
	seen: set[str] = set()
	page_one = [
		{"friendId": 1, "geekCard": {"geekId": "g1", "securityId": "s1", "name": "同名候选人"}},
		{"friendId": 2, "geekCard": {"geekId": "g2", "securityId": "s2", "name": "同名候选人"}},
	]
	page_two = [
		{"friendId": 1, "geekCard": {"geekId": "g1", "securityId": "s1", "name": "同名候选人"}},
		{"friendId": 3, "geekCard": {"geekId": "g3", "securityId": "s3", "name": "新候选人"}},
	]

	first = _dedupe_candidate_items(page_one, seen, extract_candidate_ref)
	second = _dedupe_candidate_items(page_two, seen, extract_candidate_ref)

	assert len(first) == 2
	assert [extract_candidate_ref(item)["geek_id"] for item in second] == ["g3"]


def test_candidate_page_dedup_keeps_records_without_any_stable_identifier():
	seen: set[str] = set()
	items = [{"name": "Unknown A"}, {"name": "Unknown A"}]
	assert _dedupe_candidate_items(items, seen, extract_candidate_ref) == items
