from types import SimpleNamespace

import pytest

from boss_agent_cli.web import WebConsoleError
from boss_agent_cli.web.server import RecruiterRequestHandler


def test_negative_content_length_is_rejected() -> None:
	handler = SimpleNamespace(headers={"Content-Length": "-1"})
	with pytest.raises(WebConsoleError) as caught:
		RecruiterRequestHandler._read_json(handler)
	assert caught.value.code == "INVALID_LENGTH"
	assert caught.value.status == 400


def test_zero_content_length_remains_valid_empty_payload() -> None:
	handler = SimpleNamespace(headers={"Content-Length": "0"})
	assert RecruiterRequestHandler._read_json(handler) == {}


def test_non_numeric_content_length_is_rejected() -> None:
	handler = SimpleNamespace(headers={"Content-Length": "nope"})
	with pytest.raises(WebConsoleError) as caught:
		RecruiterRequestHandler._read_json(handler)
	assert caught.value.code == "INVALID_LENGTH"
