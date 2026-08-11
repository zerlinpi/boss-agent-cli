"""Recruiter automation engine for boss-agent-cli."""

from boss_agent_cli.automation.models import (
	ActionResult,
	AutomationMode,
	Conversation,
	ConversationRef,
	Decision,
	PlatformAction,
	RunReport,
)
from boss_agent_cli.automation.state_validation import install_nested_state_validation
from boss_agent_cli.automation.storage import AutomationStore

install_nested_state_validation(AutomationStore)

__all__ = [
	"ActionResult",
	"AutomationMode",
	"Conversation",
	"ConversationRef",
	"Decision",
	"PlatformAction",
	"RunReport",
]
