import json

import pytest
from click.testing import CliRunner

from boss_agent_cli.config import load_config
from boss_agent_cli.main import _parse_delay_range, cli


@pytest.mark.parametrize("value", ["nan-3", "1-inf", "3-1", "1--2", "bad"])
def test_direct_delay_range_rejects_invalid_values(value: str) -> None:
	with pytest.raises(Exception):
		_parse_delay_range(value)


def test_direct_delay_range_accepts_valid_values() -> None:
	assert _parse_delay_range("0-0") == (0.0, 0.0)
	assert _parse_delay_range("1.5-3") == (1.5, 3.0)


def test_invalid_persisted_role_falls_back_to_candidate(tmp_path) -> None:
	path = tmp_path / "config.json"
	path.write_text(json.dumps({"role": "administrator"}), encoding="utf-8")
	assert load_config(path)["role"] == "candidate"


def test_data_dir_creation_failure_uses_structured_cli_error(tmp_path) -> None:
	file_path = tmp_path / "not-a-directory"
	file_path.write_text("occupied", encoding="utf-8")
	result = CliRunner().invoke(cli, ["--data-dir", str(file_path), "--json", "status"])

	assert result.exit_code == 0
	payload = json.loads(result.output)
	assert payload["ok"] is False
	assert payload["error"]["code"] == "INVALID_PARAM"
	assert "数据目录" in payload["error"]["message"]
