import math

import pytest

from boss_agent_cli.automation.config import automation_config_from_dict


def test_explicit_empty_allowed_actions_stays_empty() -> None:
	config = automation_config_from_dict({"allowed_actions": []})
	assert config.allowed_actions == ()


def test_unknown_allowed_actions_do_not_expand_to_defaults() -> None:
	config = automation_config_from_dict({"allowed_actions": ["typo-action"]})
	assert config.allowed_actions == ()


def test_nonfinite_automation_thresholds_are_rejected() -> None:
	with pytest.raises(ValueError, match="human_review_threshold"):
		automation_config_from_dict({"human_review_threshold": math.nan})
	with pytest.raises(ValueError, match="auto_execute_threshold"):
		automation_config_from_dict({"auto_execute_threshold": math.inf})


def test_reversed_automation_thresholds_are_rejected() -> None:
	with pytest.raises(ValueError, match="human_review_threshold <= auto_execute_threshold"):
		automation_config_from_dict({"human_review_threshold": 0.9, "auto_execute_threshold": 0.8})


def test_fractional_and_negative_limits_are_rejected() -> None:
	with pytest.raises(ValueError, match="max_actions_per_run"):
		automation_config_from_dict({"max_actions_per_run": 1.5})
	with pytest.raises(ValueError, match="max_consecutive_errors"):
		automation_config_from_dict({"max_consecutive_errors": -1})


def test_scalar_lists_are_rejected_instead_of_iterating_characters() -> None:
	with pytest.raises(ValueError, match="tabs"):
		automation_config_from_dict({"tabs": "未读"})
	with pytest.raises(ValueError, match="allowed_actions"):
		automation_config_from_dict({"allowed_actions": "send_follow_up"})
