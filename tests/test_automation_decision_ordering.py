from boss_agent_cli.automation import decision as decision_module
from boss_agent_cli.automation.config import AutomationConfig
from boss_agent_cli.automation.models import Conversation


def test_prior_questionnaire_does_not_reclassify_older_incoming_as_reply() -> None:
	config = AutomationConfig()
	conversation = Conversation(
		title="candidate",
		incoming_messages=("older candidate message",),
		ordered_messages=(),
	)
	status = decision_module._conversation_status(
		conversation,
		{"questionnaire_sent_at": "2026-08-11T00:00:00+00:00"},
		config,
	)
	assert status.has_questionnaire is True
	assert status.candidate_after_questionnaire is False


def test_unordered_outgoing_and_incoming_collections_are_not_assumed_chronological() -> None:
	config = AutomationConfig()
	conversation = Conversation(
		title="candidate",
		outgoing_messages=(config.questionnaire_message,),
		incoming_messages=("reply maybe before or after",),
		ordered_messages=(),
	)
	status = decision_module._conversation_status(conversation, {}, config)
	assert status.has_questionnaire is True
	assert status.candidate_after_questionnaire is False


def test_ordered_message_after_questionnaire_is_valid_reply_evidence() -> None:
	config = AutomationConfig()
	conversation = Conversation(
		title="candidate",
		incoming_messages=("yes",),
		ordered_messages=(
			("outgoing", config.questionnaire_message),
			("incoming", "yes"),
		),
	)
	status = decision_module._conversation_status(conversation, {}, config)
	assert status.candidate_after_questionnaire is True


def test_prior_follow_up_does_not_reclassify_historical_incoming() -> None:
	config = AutomationConfig()
	conversation = Conversation(
		title="candidate",
		incoming_messages=("historical reply",),
		ordered_messages=(),
	)
	status = decision_module._conversation_status(
		conversation,
		{"follow_up_sent_at": "2026-08-11T00:00:00+00:00"},
		config,
	)
	assert status.has_follow_up is True
	assert status.candidate_after_follow_up is False


def test_partial_ordered_window_does_not_hide_older_questionnaire_marker() -> None:
	config = AutomationConfig()
	conversation = Conversation(
		title="candidate",
		outgoing_messages=(config.questionnaire_message,),
		incoming_messages=("older incoming",),
		ordered_messages=(("incoming", "recent unrelated message"),),
	)
	status = decision_module._conversation_status(conversation, {}, config)
	assert status.has_questionnaire is True
	assert status.candidate_after_questionnaire is False


def test_partial_ordered_window_does_not_hide_exchange_marker() -> None:
	config = AutomationConfig()
	conversation = Conversation(
		title="candidate",
		outgoing_messages=("已交换微信",),
		ordered_messages=(("incoming", "recent message"),),
	)
	status = decision_module._conversation_status(conversation, {}, config)
	assert status.has_exchange is True
