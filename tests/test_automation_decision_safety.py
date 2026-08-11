from boss_agent_cli.automation.config import AutomationConfig
from boss_agent_cli.automation.decision import decide_action, snapshot_from_conversation
from boss_agent_cli.automation.execution import status_for_decision
from boss_agent_cli.automation.models import Conversation, EventStatus, PlatformAction


def test_explicit_interview_time_creates_local_lead_without_job_fit_score() -> None:
	conversation = Conversation(
		title="candidate",
		incoming_messages=("明天下午3点可以",),
	)
	decision = decide_action(
		conversation,
		AutomationConfig(),
		{"exchange_contact_at": "2026-08-11T00:00:00+00:00"},
	)
	assert decision.action is PlatformAction.CREATE_INTERVIEW_LEAD
	assert decision.confidence == 0.95
	assert decision.interview_time == "明天下午3:00"
	assert "local scheduling lead" in decision.reason


def test_interview_lead_obeys_allowed_actions() -> None:
	conversation = Conversation(
		title="candidate",
		incoming_messages=("明天下午3点可以",),
	)
	decision = decide_action(
		conversation,
		AutomationConfig(),
		{"exchange_contact_at": "2026-08-11T00:00:00+00:00"},
	)
	config = AutomationConfig(allowed_actions=())
	assert status_for_decision(config, decision, dry_run=False) is EventStatus.QUEUED_PENDING_ACTION


def test_snapshot_does_not_extract_generic_job_fit_fields() -> None:
	conversation = Conversation(
		title="候选人",
		incoming_messages=("北京 本科 8年经验，有兴趣，今天在线",),
	)
	snapshot = snapshot_from_conversation(conversation)
	assert snapshot.city == ""
	assert snapshot.education == ""
	assert snapshot.experience_years is None
	assert "有兴趣" in snapshot.intent_signals
	assert snapshot.last_active_at == "active"
