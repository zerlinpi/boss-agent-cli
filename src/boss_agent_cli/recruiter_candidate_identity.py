"""Stable candidate identity for local recruiter workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import boss_agent_cli.recruiter_ai_models as model_module
import boss_agent_cli.recruiter_ai_store as store_module

_INSTALLED = False


def _normalized_source_path(value: Any) -> str:
	text = str(value or "").strip()
	if not text:
		return ""
	try:
		text = str(Path(text).expanduser().resolve(strict=False))
	except (OSError, RuntimeError):
		pass
	text = re.sub(r"/+", "/", text.replace("\\", "/"))
	if re.match(r"^[A-Za-z]:/", text):
		text = text.casefold()
	return text


def install_stable_local_candidate_identity() -> None:
	"""Use a local file path as identity while keeping resume content as the change fingerprint."""
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
		return original(resume, source)

	setattr(candidate_key, "_boss_local_path_stable", True)
	model_module.candidate_key = candidate_key
	store_module.candidate_key = candidate_key
