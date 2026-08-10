import json

import pytest

from boss_agent_cli.commands.config_cmd import _parse_value, _validate_value
from boss_agent_cli.config import DEFAULTS, load_config


def test_runtime_invalid_delays_fall_back_to_defaults(tmp_path) -> None:
	path = tmp_path / "config.json"
	path.write_text(
		json.dumps({
			"request_delay": [5, 1],
			"batch_greet_delay": [0, "bad"],
		}),
		encoding="utf-8",
	)

	config = load_config(path)
	assert config["request_delay"] == DEFAULTS["request_delay"]
	assert config["batch_greet_delay"] == DEFAULTS["batch_greet_delay"]


def test_runtime_invalid_nested_sections_fall_back_to_defaults(tmp_path) -> None:
	path = tmp_path / "config.json"
	path.write_text(json.dumps({"automation": "bad", "crawl": []}), encoding="utf-8")

	config = load_config(path)
	assert config["automation"] == DEFAULTS["automation"]
	assert config["crawl"] == DEFAULTS["crawl"]


def test_cli_dict_config_requires_json_object() -> None:
	with pytest.raises(ValueError, match="JSON object"):
		_parse_value('["not", "object"]', DEFAULTS["automation"])

	parsed = _parse_value('{"mode":"assisted"}', DEFAULTS["automation"])
	assert parsed == {"mode": "assisted"}


def test_cli_delay_validation_rejects_wrong_shape_and_order() -> None:
	with pytest.raises(ValueError):
		_validate_value("request_delay", [1.0])
	with pytest.raises(ValueError):
		_validate_value("request_delay", [2.0, 1.0])
	_validate_value("request_delay", [0.1, 1.5])
