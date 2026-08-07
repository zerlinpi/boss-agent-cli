from __future__ import annotations

from boss_agent_cli.commands.recruiter.ai_platform import _candidate_ref_key
from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def test_cli_candidate_ref_key_uses_stable_platform_identifiers():
	assert _candidate_ref_key({"geek_id": "g1", "security_id": "s1", "friend_id": 1}) == "geek_id:g1"
	assert _candidate_ref_key({"geek_id": "", "security_id": "s1", "friend_id": 1}) == "security_id:s1"
	assert _candidate_ref_key({"geek_id": "", "security_id": "", "friend_id": 1}) == "friend_id:1"
	assert _candidate_ref_key({"name": "same-name"}) is None


def test_final_app_asset_contains_clipboard_fallback(tmp_path):
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	try:
		content, content_type = application.asset("app.js")
		text = content.decode("utf-8")
		assert "safeCopy" in text
		assert "document.execCommand(\"copy\")" in text
		assert "data-copy-text" in text
		assert content_type == "application/javascript; charset=utf-8"
	finally:
		application.tasks.close()
