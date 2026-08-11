from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_package_has_double_click_entrypoint() -> None:
	launcher = (ROOT / "package-recruiter-local.bat").read_text(encoding="utf-8")
	assert "scripts\\package-recruiter-local.ps1" in launcher


def test_local_package_uses_explicit_runtime_allowlist() -> None:
	script = (ROOT / "scripts" / "package-recruiter-local.ps1").read_text(encoding="utf-8")

	for required in (
		"Copy-PackageItem 'src' $StageRoot",
		"Copy-PackageItem 'scripts\\start-recruiter-web.ps1' $StageRoot",
		"Copy-PackageItem 'start-recruiter-web.bat' $StageRoot",
		"Copy-PackageItem 'pyproject.toml' $StageRoot",
		"Copy-PackageItem 'README.md' $StageRoot",
		"Copy-PackageItem 'LICENSE' $StageRoot",
	):
		assert required in script

	for forbidden in (
		"Copy-PackageItem '.venv'",
		"Copy-PackageItem '.git'",
		"Copy-PackageItem '.boss-agent'",
		"Copy-PackageItem 'tests'",
	):
		assert forbidden not in script

	assert "Compress-Archive -Path $StageRoot" in script
	assert "Local recruiter data, login credentials and API keys are NOT included" in script


def test_local_package_start_here_keeps_only_key_first_run_flow() -> None:
	script = (ROOT / "scripts" / "package-recruiter-local.ps1").read_text(encoding="utf-8")

	assert "AI -> BOSS login -> Research -> 5-candidate validation" in script
	assert "start-recruiter-web.bat" in script
