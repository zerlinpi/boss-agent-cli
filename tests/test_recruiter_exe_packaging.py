from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_exe_builder_has_double_click_entrypoint() -> None:
	launcher = (ROOT / "build-recruiter-exe.bat").read_text(encoding="utf-8")
	assert "scripts\\build-recruiter-exe.ps1" in launcher


def test_exe_builder_uses_windowed_onedir_and_desktop_entrypoint() -> None:
	script = (ROOT / "scripts" / "build-recruiter-exe.ps1").read_text(encoding="utf-8")

	for required in (
		"--onedir",
		"--windowed",
		"--name BossRecruitAI",
		"--collect-all boss_agent_cli",
		"--collect-all webview",
		"src\\boss_agent_cli\\desktop.py",
		"BossRecruitAI.exe",
		"Compress-Archive",
	):
		assert required in script

	assert "Login credentials and API keys are not included" in script
	assert ".venv-build" in script
	assert "64-bit Python 3.10-3.14" in script
	assert "auth sessions, API keys or local recruiter data" in script


def test_exe_release_instructions_keep_only_main_product_flow() -> None:
	script = (ROOT / "scripts" / "build-recruiter-exe.ps1").read_text(encoding="utf-8")

	assert "Configure AI -> Log in to BOSS -> Enable Research -> Run 5-candidate validation" in script
	assert "use Autopilot for daily incremental screening" in script
	assert "BOSS login can open a separate Chrome/Edge window" in script
