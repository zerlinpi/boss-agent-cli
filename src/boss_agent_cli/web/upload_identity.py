"""Stable identities for browser-uploaded recruiter resumes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import boss_agent_cli.recruiter_ai_store as recruiter_store_module
from boss_agent_cli.recruiter_ai import candidate_name, extract_contact_details, resume_fingerprint
from boss_agent_cli.recruiter_ai_models import stable_hash

_INSTALLED = False
_GENERIC_UPLOAD_NAMES = {"candidate", "resume", "cv", "简历"}


def _normalized_contacts(resume: dict[str, Any]) -> list[str]:
	contacts = extract_contact_details(resume)
	return sorted(
		f"{kind}:{str(value).strip().casefold()}"
		for kind, values in contacts.items()
		for value in values
		if str(value).strip()
	)


def _web_upload_key(resume: dict[str, Any], filename: str) -> str:
	name = candidate_name(resume).strip().casefold()
	stem = Path(filename).stem.strip().casefold()
	contacts = _normalized_contacts(resume)

	if contacts:
		# Contacts are strong recruiter-side identity signals. Hash the normalized values so the
		# candidate key itself never stores a phone number, email, WeChat ID, or QQ value.
		identity: dict[str, Any] = {"contacts_hash": stable_hash(contacts)}
		if name and name not in _GENERIC_UPLOAD_NAMES and name != stem:
			identity["name"] = name
		return f"web-upload:{stable_hash(identity)[:24]}"

	identity = {"filename": filename, "name": name}
	# Non-JSON uploads currently use the file stem as the provisional candidate name. Two unrelated
	# people can therefore both arrive as `resume.pdf`. In that weak-identity case, include the
	# model-safe resume fingerprint so distinct files cannot collapse into one logical candidate.
	if not name or name in _GENERIC_UPLOAD_NAMES or name == stem:
		identity["resume_fingerprint"] = resume_fingerprint(resume)
	return f"web-upload:{stable_hash(identity)[:24]}"


def install_web_upload_identity() -> None:
	"""Prevent same-named browser uploads from being grouped as the same candidate."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	original: Callable[[dict[str, Any], dict[str, Any] | None], str] = recruiter_store_module.candidate_key
	if getattr(original, "_boss_web_upload_collision_safe", False):
		return

	def candidate_key(resume: dict[str, Any], source: dict[str, Any] | None = None) -> str:
		source = source or {}
		filename = str(source.get("filename") or "").strip().casefold()
		if source.get("type") == "web-upload" and filename:
			return _web_upload_key(resume, filename)
		return original(resume, source)

	setattr(candidate_key, "_boss_web_upload_collision_safe", True)
	setattr(recruiter_store_module, "candidate_key", candidate_key)
