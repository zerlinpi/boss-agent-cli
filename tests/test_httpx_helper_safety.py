import pytest

from boss_agent_cli.api.httpx_helpers import add_stoken_to_get_params


def test_stoken_injection_does_not_mutate_caller_params() -> None:
	original = {"page": 1}
	kwargs = {"params": original}

	add_stoken_to_get_params("GET", kwargs, "secret")

	assert original == {"page": 1}
	assert kwargs["params"] == {"page": 1, "__zp_stoken__": "secret"}
	assert kwargs["params"] is not original


def test_stoken_injection_accepts_none_and_lowercase_method() -> None:
	kwargs = {"params": None}
	add_stoken_to_get_params("get", kwargs, "secret")
	assert kwargs["params"] == {"__zp_stoken__": "secret"}


def test_stoken_injection_rejects_invalid_params_shape() -> None:
	with pytest.raises(TypeError, match="GET params"):
		add_stoken_to_get_params("GET", {"params": 42}, "secret")
