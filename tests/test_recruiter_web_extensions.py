from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def test_recruiter_web_bundle_includes_reply_safety_and_contact_extensions(tmp_path):
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed-token")
	try:
		javascript, content_type = application.asset("app.js")
		styles, style_type = application.asset("styles.css")
		assert b"replySafetyMarkup" in javascript
		assert b"renderCandidateDrawerWithContacts" in javascript
		assert b"reply-safety-warning" in styles
		assert b"contact-retention-section" in styles
		assert "javascript" in content_type
		assert "css" in style_type
	finally:
		application.tasks.close()
