import json

import pytest

from boss_agent_cli.automation.storage import AutomationStorageError, AutomationStore


def _write_state(store: AutomationStore, payload) -> None:
	store.state_path.write_text(json.dumps(payload), encoding="utf-8")


def test_candidate_prior_must_be_object(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	_write_state(store, {"conversations": {"candidate": []}, "autonomy": {}, "safety": {}})
	with pytest.raises(AutomationStorageError, match="conversations"):
		store.read_state()


def test_circuit_breaker_must_be_object(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	_write_state(store, {"conversations": {}, "autonomy": {"circuit_breaker": []}, "safety": {}})
	with pytest.raises(AutomationStorageError, match="circuit_breaker"):
		store.read_state()


def test_consecutive_errors_must_be_nonnegative_integer(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	_write_state(store, {"conversations": {}, "autonomy": {}, "safety": {"consecutive_errors": -1}})
	with pytest.raises(AutomationStorageError, match="consecutive_errors"):
		store.read_state()


def test_inflight_action_requires_valid_action_and_confidence(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	_write_state(store, {
		"conversations": {
			"candidate": {
				"inflight_action": {"action": "not-real", "confidence": 0.8},
			}
		},
		"autonomy": {},
		"safety": {},
	})
	with pytest.raises(AutomationStorageError, match="inflight_action.action"):
		store.read_state()

	_write_state(store, {
		"conversations": {
			"candidate": {
				"inflight_action": {"action": "send_follow_up", "confidence": float("nan")},
			}
		},
		"autonomy": {},
		"safety": {},
	})
	with pytest.raises(AutomationStorageError, match="confidence"):
		store.read_state()


def test_valid_nested_state_roundtrips(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	state = {
		"conversations": {
			"candidate": {
				"inflight_action": {
					"action": "send_follow_up",
					"confidence": 0.9,
					"started_at": "2026-08-11T00:00:00+00:00",
					"message": "hello",
					"status": "executing",
				}
			}
		},
		"autonomy": {"circuit_breaker": {"open": False, "reason": ""}},
		"safety": {"consecutive_errors": 0},
	}
	store.write_state(state)
	assert store.read_state()["conversations"]["candidate"]["inflight_action"]["action"] == "send_follow_up"
