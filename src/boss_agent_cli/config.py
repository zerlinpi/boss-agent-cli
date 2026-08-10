import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
	"request_delay": [1.5, 3.0],
	"batch_greet_delay": [2.0, 5.0],
	"log_level": "error",
	"cdp_url": None,
	"export_dir": None,
	"platform": "zhipin",
	"role": "candidate",
	"operating_mode": "assisted",
	"low_risk_mode": True,
	"automation": {
		"mode": "autonomous",
		"platforms": ["zhilian", "zhipin"],
		"allowed_actions": [
			"scan_conversations",
			"read_candidate_profile",
			"send_questionnaire",
			"send_follow_up",
			"exchange_contact",
			"create_interview_lead",
		],
		"human_review_threshold": 0.65,
		"auto_execute_threshold": 0.82,
	},
	"crawl": {
		"chrome_path": None,
		"cdp_port": None,
		"hook_profile": "none",
		"hook_dir": None,
		"max_requests": 20,
		"max_details": 50,
		"max_seconds": 600,
		"max_retries": 1,
	},
}


def _merge_config(defaults: dict[str, Any], user_cfg: dict[str, Any]) -> dict[str, Any]:
	"""Merge top-level user settings while retaining missing nested default fields."""
	cfg = deepcopy(defaults)
	for key, value in user_cfg.items():
		current = cfg.get(key)
		if isinstance(current, dict) and isinstance(value, dict):
			merged = deepcopy(current)
			merged.update(deepcopy(value))
			cfg[key] = merged
		else:
			cfg[key] = deepcopy(value)
	return cfg


def load_config(config_path: Path | None) -> dict[str, Any]:
	user_cfg: dict[str, Any] = {}
	if config_path and config_path.exists():
		try:
			with open(config_path, encoding="utf-8") as handle:
				loaded = json.load(handle)
		except (OSError, json.JSONDecodeError, UnicodeDecodeError):
			loaded = None
		if isinstance(loaded, dict):
			user_cfg = loaded

	cfg = _merge_config(DEFAULTS, user_cfg)
	mode = user_cfg.get("operating_mode")
	if mode not in {"assisted", "research"}:
		if "low_risk_mode" in user_cfg:
			mode = "research" if user_cfg["low_risk_mode"] is False else "assisted"
		else:
			mode = DEFAULTS.get("operating_mode", "assisted")
	if mode not in {"assisted", "research"}:
		mode = "assisted"
	cfg["operating_mode"] = mode
	cfg["low_risk_mode"] = mode != "research"
	return cfg
