import threading

import pytest

import boss_agent_cli.config as config_module
from boss_agent_cli.config import ConfigLockBusy, read_user_config, update_user_config
from boss_agent_cli.web import RecruiterWebController


def test_concurrent_config_updates_preserve_unrelated_keys(tmp_path) -> None:
	path = tmp_path / "config.json"
	barrier = threading.Barrier(3)
	errors = []

	def write(key, value):
		try:
			barrier.wait()
			update_user_config(path, updates={key: value})
		except Exception as exc:
			errors.append(exc)

	first = threading.Thread(target=write, args=("cdp_url", "http://localhost:9222"))
	second = threading.Thread(target=write, args=("log_level", "debug"))
	first.start()
	second.start()
	barrier.wait()
	first.join()
	second.join()

	assert errors == []
	assert read_user_config(path) == {
		"cdp_url": "http://localhost:9222",
		"log_level": "debug",
	}


def test_web_mode_update_preserves_existing_cli_overrides(tmp_path) -> None:
	path = tmp_path / "config.json"
	update_user_config(path, updates={"cdp_url": "http://localhost:9222", "log_level": "debug"})
	controller = RecruiterWebController(tmp_path)

	controller.set_operating_mode("research")

	stored = read_user_config(path)
	assert stored["cdp_url"] == "http://localhost:9222"
	assert stored["log_level"] == "debug"
	assert stored["operating_mode"] == "research"
	assert stored["low_risk_mode"] is False


def test_live_config_lock_is_not_stolen(tmp_path, monkeypatch) -> None:
	path = tmp_path / "config.json"
	lock_path = tmp_path / "config.json.lock"
	lock_path.write_text("busy", encoding="utf-8")
	monkeypatch.setattr(config_module, "_CONFIG_LOCK_TIMEOUT", 0.0)

	with pytest.raises(ConfigLockBusy):
		update_user_config(path, updates={"log_level": "debug"})

	assert lock_path.exists()
