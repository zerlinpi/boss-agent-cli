from boss_agent_cli.web import controller as controller_module  # installs Web extensions
from boss_agent_cli.web.boss_draft_scope import _DRAFT_SCOPE


def _candidate(geek_id: str, friend_id: int):
	return {
		"friendId": friend_id,
		"geekCard": {"geekId": geek_id, "securityId": f"sec-{geek_id}", "name": geek_id},
		"jobCard": {"encJobId": "job-1"},
	}


def test_candidate_items_deduplicate_across_pages_inside_boss_screen_scope() -> None:
	token = _DRAFT_SCOPE.set({
		"job_key": "java",
		"job_id": "job-1",
		"existing_ids": set(),
		"draft_top": 0,
		"rank_calls": 0,
		"seen_refs": set(),
	})
	try:
		page_one = controller_module.candidate_items({"friendList": [_candidate("g1", 1), _candidate("g2", 2)]})
		page_two = controller_module.candidate_items({"friendList": [_candidate("g2", 2), _candidate("g3", 3)]})
	finally:
		_DRAFT_SCOPE.reset(token)

	assert [item["geekCard"]["geekId"] for item in page_one] == ["g1", "g2"]
	assert [item["geekCard"]["geekId"] for item in page_two] == ["g3"]
