"""Stable candidate identity and legacy source normalization for recruiter workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import boss_agent_cli.recruiter_ai_models as model_module
import boss_agent_cli.recruiter_ai_store as store_module

_INSTALLED = False
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def normalize_friend_id(value: Any) -> int | None:
	"""Return the positive integer friend id required by recruiter chat APIs."""
	if isinstance(value, bool) or value in (None, ""):
		return None
	try:
		parsed = int(str(value).strip())
	except (TypeError, ValueError):
		return None
	return parsed if parsed > 0 else None


def normalize_record_source(record: dict[str, Any]) -> dict[str, Any]:
	"""Normalize legacy source references without mutating persisted history."""
	source = record.get("source")
	if not isinstance(source, dict):
		return record
	clean_source = dict(source)
	if "friend_id" in clean_source:
		clean_source["friend_id"] = normalize_friend_id(clean_source.get("friend_id"))
	clean = dict(record)
	clean["source"] = clean_source
	return clean


def _normalized_source_path(value: Any) -> str:
	text = str(value or "").strip()
	if not text:
		return ""
	# Preserve Windows absolute paths when historical data is read on another operating system;
	# resolving C:\\... with a POSIX Path would incorrectly prefix the current working directory.
	if _WINDOWS_ABSOLUTE.match(text):
		return re.sub(r"/+", "/", text.replace("\\", "/")).casefold()
	try:
		text = str(Path(text).expanduser().resolve(strict=False))
	except (OSError, RuntimeError):
		pass
	return re.sub(r"/+", "/", text.replace("\\", "/"))


def install_stable_local_candidate_identity() -> None:
	"""Install stable local-path and recruiter-platform candidate identities."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	original: Callable[[dict[str, Any], dict[str, Any] | None], str] = model_module.candidate_key
	if getattr(original, "_boss_local_path_stable", False):
		return

	def candidate_key(resume: dict[str, Any], source: dict[str, Any] | None = None) -> str:
		source = source or {}
		path = _normalized_source_path(source.get("path"))
		if path:
			identity = {
				"type": str(source.get("type") or "local").strip().lower() or "local",
				"path": path,
			}
			return f"local-path:{model_module.stable_hash(identity)[:24]}"

		source_type = str(source.get("type") or "candidate").strip().lower() or "candidate"
		for key in ("geek_id", "candidate_id", "friend_id"):
			value = source.get(key)
			if value not in (None, ""):
				return f"{source_type}:{key}:{value}"
		return original(resume, source)

	setattr(candidate_key, "_boss_local_path_stable", True)
	model_module.candidate_key = candidate_key
	store_module.candidate_key = candidate_key
