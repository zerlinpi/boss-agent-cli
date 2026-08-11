import math

import pytest

from boss_agent_cli.automation.config import automation_config_from_dict


def test_explicit_empty_allowed_actions_stays_empty() -> None:
	config = automation_config_from_dict({"allowed_actions": []})
	assert config.allowed_actions == ()


def test_unknown_allowed_actions_are_rejected() -> None:
	with pytest.raises(ValueError, match="未知动作"):
		automation_config_from_dict({"allowed_actions": ["typo-action"]})


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


def test_automation_platforms_must_be_supported_and_nonempty() -> None:
	with pytest.raises(ValueError, match="platforms 不能为空"):
		automation_config_from_dict({"platforms": []})
	with pytest.raises(ValueError, match="不支持"):
		automation_config_from_dict({"platforms": ["unknown"]})
	config = automation_config_from_dict({"platforms": ["zhipin", "zhipin", "zhilian"]})
	assert config.platforms == ("zhipin", "zhilian")


def test_default_risk_markers_cannot_be_removed() -> None:
	config = automation_config_from_dict({"stop_on_page_text": []})
	assert "验证码" in config.stop_on_page_text
	assert "安全验证" in config.stop_on_page_text
	assert "操作频繁" in config.stop_on_page_text


def test_custom_risk_markers_extend_defaults_without_duplicates() -> None:
	config = automation_config_from_dict({"stop_on_page_text": ["验证码", "自定义风险提示"]})
	assert config.stop_on_page_text.count("验证码") == 1
	assert "自定义风险提示" in config.stop_on_page_text
