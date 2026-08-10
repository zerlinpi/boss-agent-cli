import json

from boss_agent_cli.config import DEFAULTS, load_config


def test_malformed_global_config_falls_back_to_safe_defaults(tmp_path) -> None:
	path = tmp_path / "config.json"
	path.write_text("{not-json", encoding="utf-8")

	config = load_config(path)
	assert config["operating_mode"] == "assisted"
	assert config["low_risk_mode"] is True
	assert config["request_delay"] == DEFAULTS["request_delay"]


def test_non_object_global_config_falls_back_to_safe_defaults(tmp_path) -> None:
	path = tmp_path / "config.json"
	path.write_text('["unexpected"]', encoding="utf-8")
	assert load_config(path)["platform"] == DEFAULTS["platform"]


def test_partial_nested_config_retains_missing_defaults(tmp_path) -> None:
	path = tmp_path / "config.json"
	path.write_text(json.dumps({"automation": {"mode": "assisted"}}), encoding="utf-8")

	config = load_config(path)
	assert config["automation"]["mode"] == "assisted"
	assert config["automation"]["allowed_actions"] == DEFAULTS["automation"]["allowed_actions"]


def test_loaded_nested_config_does_not_mutate_global_defaults(tmp_path) -> None:
	config = load_config(None)
	config["automation"]["allowed_actions"].append("mutated")
	config["crawl"]["max_requests"] = 999

	fresh = load_config(None)
	assert "mutated" not in fresh["automation"]["allowed_actions"]
	assert fresh["crawl"]["max_requests"] == DEFAULTS["crawl"]["max_requests"]


def test_legacy_low_risk_flag_still_migrates_operating_mode(tmp_path) -> None:
	path = tmp_path / "config.json"
	path.write_text(json.dumps({"low_risk_mode": False}), encoding="utf-8")
	config = load_config(path)

	assert config["operating_mode"] == "research"
	assert config["low_risk_mode"] is False
