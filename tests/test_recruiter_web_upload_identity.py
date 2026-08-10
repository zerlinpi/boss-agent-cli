import boss_agent_cli.recruiter_ai_store as recruiter_store_module
from boss_agent_cli.web import RecruiterWebController


_SOURCE = {"type": "web-upload", "filename": "resume.pdf", "format": "pdf"}


def test_same_named_uploads_with_different_resume_content_do_not_collapse(tmp_path) -> None:
	RecruiterWebController(tmp_path)
	first = {"name": "resume", "raw_text": "Python backend engineer with payment platform ownership."}
	second = {"name": "resume", "raw_text": "Industrial designer focused on consumer hardware and CMF."}

	assert recruiter_store_module.candidate_key(first, _SOURCE) != recruiter_store_module.candidate_key(second, _SOURCE)


def test_contact_identity_survives_resume_content_updates(tmp_path) -> None:
	RecruiterWebController(tmp_path)
	first = {"name": "resume", "raw_text": "Python engineer. Phone: 13800000000. Built payments."}
	second = {"name": "resume", "raw_text": "Python tech lead. Phone: 13800000000. Built risk systems."}

	assert recruiter_store_module.candidate_key(first, _SOURCE) == recruiter_store_module.candidate_key(second, _SOURCE)
