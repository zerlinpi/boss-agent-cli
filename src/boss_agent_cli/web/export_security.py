"""CSV export hardening for recruiter-controlled spreadsheet downloads."""

from __future__ import annotations

from typing import Any

_FORMULA_PREFIXES = ("=", "+", "-", "@")
_LEADING_IGNORABLE = " \t\r\n\v\f"


def safe_csv_cell(value: Any) -> Any:
	"""Prefix cells that could become formulas after spreadsheet whitespace normalization."""
	if not isinstance(value, str):
		return value
	candidate = value.lstrip(_LEADING_IGNORABLE)
	return "'" + value if candidate.startswith(_FORMULA_PREFIXES) else value


def install_export_security(controller_module: Any) -> None:
	"""Install the hardened helper without duplicating the controller implementation."""
	setattr(controller_module, "_csv_cell", safe_csv_cell)
