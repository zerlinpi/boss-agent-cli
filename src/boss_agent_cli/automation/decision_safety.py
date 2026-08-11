"""Conservative conversation-ordering semantics for automation decisions."""

from __future__ import annotations

from typing import Any

from boss_agent_cli.automation import decision as decision_module
from boss_agent_cli.automation.config import AutomationConfig
from boss_agent_cli.automation.models import Conversation

_INSTALLED = False


def install_decision_ordering_safety() -> None:
	"""Do not infer a post-message reply from unordered historical incoming messages."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	def conversation_status(
		conversation: Conversation,
		prior: dict[str, str],
		config: AutomationConfig,
	) -> Any:
		# Only ordered_messages can prove that an incoming message occurred after a
		# specific outbound questionnaire/follow-up. outgoing_messages + incoming_messages
		# are grouped collections, not a chronology, so they are useful for detecting
		# that a message existed but not for inferring reply order.
		ordered_texts = [message[1] for message in conversation.ordered_messages]
		fallback_texts = [*conversation.outgoing_messages, *conversation.incoming_messages]
		search_texts = ordered_texts or fallback_texts
		questionnaire_index = decision_module._last_index(search_texts, config.questionnaire_message)
		follow_up_index = decision_module._last_index(search_texts, config.follow_up_message)
		latest_incoming = "\n".join(conversation.incoming_messages)

		ordered_questionnaire_index = decision_module._last_index(ordered_texts, config.questionnaire_message)
		ordered_follow_up_index = decision_module._last_index(ordered_texts, config.follow_up_message)
		return decision_module.ConversationStatus(
			has_questionnaire=questionnaire_index >= 0 or bool(prior.get("questionnaire_sent_at")),
			has_follow_up=follow_up_index >= 0 or bool(prior.get("follow_up_sent_at")),
			has_exchange=bool(prior.get("exchange_contact_at")) or any(
				"交换微信" in text or "已交换" in text for text in search_texts
			),
			candidate_after_questionnaire=(
				ordered_questionnaire_index >= 0
				and decision_module._has_incoming_after(conversation, ordered_questionnaire_index)
			),
			candidate_after_follow_up=(
				ordered_follow_up_index >= 0
				and decision_module._has_incoming_after(conversation, ordered_follow_up_index)
			),
			interview_time=decision_module._extract_interview_time(latest_incoming),
		)

	decision_module._conversation_status = conversation_status
