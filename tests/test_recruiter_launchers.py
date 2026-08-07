from pathlib import Path

import pytest

from boss_agent_cli.web.container_main import _port


ROOT = Path(__file__).resolve().parents[1]


def test_container_port_defaults_and_validates(monkeypatch):
    monkeypatch.delenv("BOSS_WEB_PORT", raising=False)
    assert _port() == 8765

    monkeypatch.setenv("BOSS_WEB_PORT", "9000")
    assert _port() == 9000

    for value in ("0", "65536", "not-a-port"):
        monkeypatch.setenv("BOSS_WEB_PORT", value)
        with pytest.raises(SystemExit):
            _port()


def test_recruiter_compose_publishes_loopback_only():
    compose = (ROOT / "docker-compose.recruiter.yml").read_text(encoding="utf-8")
    assert '127.0.0.1:${BOSS_WEB_PORT:-8765}:8765' in compose
    assert '0.0.0.0:${BOSS_WEB_PORT' not in compose
    assert "boss-recruiter-data:/data/.boss-agent" in compose


def test_recruiter_dockerfile_uses_web_entrypoint_and_healthcheck():
    dockerfile = (ROOT / "Dockerfile.recruiter-web").read_text(encoding="utf-8")
    assert 'boss_agent_cli.web.container_main' in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "USER boss" in dockerfile


def test_windows_launchers_delegate_to_bootstrap_scripts():
    native = (ROOT / "start-recruiter-web.bat").read_text(encoding="utf-8")
    docker = (ROOT / "start-recruiter-docker.bat").read_text(encoding="utf-8")
    stop_docker = (ROOT / "stop-recruiter-docker.bat").read_text(encoding="utf-8")
    assert "scripts\\start-recruiter-web.ps1" in native
    assert "scripts\\start-recruiter-docker.ps1" in docker
    assert "scripts\\stop-recruiter-docker.ps1" in stop_docker


def test_windows_native_bootstrap_installs_browser_kernel_and_supported_python_versions():
    script = (ROOT / "scripts" / "start-recruiter-web.ps1").read_text(encoding="utf-8")
    assert "patchright.exe" in script
    assert "install chromium" in script
    for version in ("-3.14", "-3.13", "-3.12", "-3.11", "-3.10"):
        assert version in script


def test_windows_docker_bootstrap_validates_host_port():
    script = (ROOT / "scripts" / "start-recruiter-docker.ps1").read_text(encoding="utf-8")
    assert "[int]::TryParse" in script
    assert "$ParsedPort -lt 1" in script
    assert "$ParsedPort -gt 65535" in script
    assert "$env:BOSS_WEB_PORT = $Port" in script
