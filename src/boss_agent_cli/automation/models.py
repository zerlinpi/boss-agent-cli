"""Typed models shared by recruiter automation subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any, NewType

CandidateKey = NewType("CandidateKey", str)
ConversationFingerprint = NewType("ConversationFingerprint", str)


@unique
class AutomationMode(str, Enum):
	ASSIST = "assist"
	TRAINING = "training"
	AUTONOMOUS = "autonomous"
	PAUSED = "paused"


@unique
class PlatformAction(str, Enum):
	SCAN_CONVERSATIONS = "scan_conversations"
	READ_CANDIDATE_PROFILE = "read_candidate_profile"
	SEND_QUESTIONNAIRE = "send_questionnaire"
	SEND_FOLLOW_UP = "send_follow_up"
	EXCHANGE_CONTACT = "exchange_contact"
	CREATE_INTERVIEW_LEAD = "create_interview_lead"
	SKIP = "skip"
	QUEUE_REVIEW = "queue_review"


@unique
class EventStatus(str, Enum):
	# EXECUTED is the adapter-level success status used by checkpointed execution.
	EXECUTED = "EXECUTED"
	AUTO_EXECUTED = "AUTO_EXECUTED"
	QUEUED_FOR_REVIEW = "QUEUED_FOR_REVIEW"
	QUEUED_PENDING_ACTION = "QUEUED_PENDING_ACTION"
	STOPPED_BY_SAFETY = "STOPPED_BY_SAFETY"
	CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
	PLATFORM_VERIFICATION_REQUIRED = "PLATFORM_VERIFICATION_REQUIRED"
	SKIPPED = "SKIPPED"
	DRY_RUN = "DRY_RUN"


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
	key: CandidateKey
	name: str
	title: str = ""
	city: str = ""
	resume_text: str = ""
	expected_salary_min: int | None = None
	expected_salary_max: int | None = None
	experience_years: float | None = None
	education: str = ""
	last_active_at: str = ""
	intent_signals: tuple[str, ...] = ()
	risk_flags: tuple[str, ...] = ()
	do_not_contact: bool = False


@dataclass(frozen=True, slots=True)
class Conversation:
	title: str
	incoming_messages: tuple[str, ...] = ()
	outgoing_messages: tuple[str, ...] = ()
	ordered_messages: tuple[tuple[str, str], ...] = ()
	all_messages: tuple[str, ...] = ()
	fingerprint: ConversationFingerprint = ConversationFingerprint("")
	item_title: str = ""
	candidate: CandidateSnapshot | None = None


@dataclass(frozen=True, slots=True)
class ConversationRef:
	id: str
	tab: str
	conversation: Conversation | None = None
	diagnostic: str = ""
	reason: str = ""


@dataclass(frozen=True, slots=True)
class MatchScore:
	pass_hard_conditions: bool
	score: int
	recommendation: str
	reason: str
	risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Decision:
	action: PlatformAction
	confidence: float
	reason: str
	candidate_key: CandidateKey
	message: str = ""
	requires_human: bool = False
	interview_time: str = ""
	matching: MatchScore | None = None
	risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionResult:
	status: str
	details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AutomationEvent:
	ts: str
	platform: str
	role: str
	candidate_key: str
	action: str
	status: str
	confidence: float
	reason: str
	result: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewItem:
	"""Human-review record with backward-compatible timestamp and scoring fields."""

	id: str
	candidate_key: str
	platform: str
	action: PlatformAction | str
	message: str = ""
	reason: str = ""
	decision_score: float = 0.0
	confidence: float = 0.0
	payload: dict[str, Any] = field(default_factory=dict)
	status: str = "review"
	created_at: str = ""
	ts: str = ""
	reviewed_at: str = ""
	rejection_reason: str = ""

	def __post_init__(self) -> None:
		self.action = PlatformAction(self.action)
		if not self.created_at and self.ts:
			self.created_at = self.ts
		if not self.ts and self.created_at:
			self.ts = self.created_at
		if not self.created_at:
			self.created_at = self.ts = ""


@dataclass
class PendingAction:
	"""Approved action waiting for execution or verification."""

	id: str
	candidate_key: str
	platform: str
	action: PlatformAction | str
	message: str = ""
	payload: dict[str, Any] = field(default_factory=dict)
	approved_review_id: str = ""
	status: str = "pending"
	created_at: str = ""
	ts: str = ""
	confidence: float = 0.0
	reason: str = ""
	decision_score: float = 0.0
	updated_at: str = ""

	def __post_init__(self) -> None:
		self.action = PlatformAction(self.action)
		if not self.created_at and self.ts:
			self.created_at = self.ts
		if not self.ts and self.created_at:
			self.ts = self.created_at
		if not self.created_at:
			self.created_at = self.ts = ""


@dataclass(frozen=True, slots=True)
class PlatformHealth:
	status: str
	checks: tuple[dict[str, Any], ...] = ()
	warning: str = ""


@dataclass(frozen=True, slots=True)
class RunReport:
	status: str
	events: tuple[AutomationEvent, ...]
	dry_run: bool
	platform: str
	mode: AutomationMode


@dataclass(slots=True)
class CycleResult:
	"""Generic cycle result used by cross-process runner wrappers."""

	cycle_id: str
	started_at: str
	finished_at: str
	duration_ms: int
	references_scanned: int
	pending_processed: int
	events: list[Any] = field(default_factory=list)
	errors: list[str] = field(default_factory=list)
	stopped: bool = False
