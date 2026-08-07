from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_native_windows_launcher_rejects_unsupported_python_and_reuses_running_workspace() -> None:
	text = (ROOT / "scripts" / "start-recruiter-web.ps1").read_text(encoding="utf-8")

	assert "(3,10) <= sys.version_info[:2] < (3,15)" in text
	assert "Test-RecruiterWorkspace $Url" in text
	assert "Recruiter workspace is already running" in text
	assert "Test-PortOpen 8765" in text
	assert "Port 8765 is already in use by another application" in text


def test_docker_windows_launcher_reuses_running_workspace_before_build() -> None:
	text = (ROOT / "scripts" / "start-recruiter-docker.ps1").read_text(encoding="utf-8")

	reuse_index = text.index("if (Test-RecruiterWorkspace $Url)")
	build_index = text.index("compose -f $ComposeFile up -d --build")
	assert reuse_index < build_index
	assert "Test-PortOpen $ParsedPort" in text
	assert "Host port $Port is already in use by another application" in text
