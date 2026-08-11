import json

import pytest

from boss_agent_cli.automation.reply_ai import parse_reply_draft


def _draft(**overrides) -> str:
	payload = {
		"action": "send_follow_up",
		"confidence": 0.9,
		"reply": "您好，可以继续沟通岗位细节。",
		"reason": "candidate replied",
		"risk_flags": [],
	}
	payload.update(overrides)
	return json.dumps(payload, ensure_ascii=False)


def test_reply_confidence_must_be_finite_unit_interval() -> None:
	with pytest.raises(TypeError, match="confidence"):
		parse_reply_draft(_draft(confidence=float("nan")))
	with pytest.raises(TypeError, match="confidence"):
		parse_reply_draft(_draft(confidence=float("inf")))
	with pytest.raises(TypeError, match="confidence"):
		parse_reply_draft(_draft(confidence=1.1))


def test_sensitive_outbound_content_forces_risk_flag() -> None:
	draft = parse_reply_draft(_draft(reply="请告知年龄、婚育情况和身体健康状况。"))
	assert "sensitive-outbound-content" in draft.risk_flags


def test_payment_language_forces_human_review_risk_flag() -> None:
	draft = parse_reply_draft(_draft(reply="请先支付押金并完成转账。"))
	assert "sensitive-outbound-content" in draft.risk_flags


def test_empty_outbound_content_is_flagged() -> None:
	draft = parse_reply_draft(_draft(reply="   "))
	assert "empty-outbound-content" in draft.risk_flags


def test_oversized_reply_is_rejected() -> None:
	with pytest.raises(TypeError, match="exceeds"):
		parse_reply_draft(_draft(reply="x" * 2001))


def test_safe_reply_roundtrips_without_added_risk() -> None:
	draft = parse_reply_draft(_draft())
	assert draft.confidence == 0.9
	assert draft.risk_flags == ()
