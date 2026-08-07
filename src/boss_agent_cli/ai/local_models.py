"""Local model manifests and filesystem registry helpers."""

from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

APPROVED_LOCAL_MODEL_LICENSES: Final = frozenset({"Apache-2.0", "MIT"})
RUNTIME_BASE_URLS: Final = {
	"ollama": "http://localhost:11434/v1",
	"vllm": "http://localhost:8000/v1",
}


@dataclass(frozen=True, slots=True)
class LocalModelManifest:
	name: str
	runtime: str
	license: str
	min_memory_gb: int
	description: str = ""
	recommended: bool = False


@dataclass(frozen=True, slots=True)
class ImportedLocalModel:
	model: str
	path: str
	runtime: str


class LocalModelManifestError(Exception):
	"""Raised when a local model manifest is not safe to register."""

	def __init__(self, code: str, message: str) -> None:
		super().__init__(message)
		self.code = code
		self.message = message


RECOMMENDED_MODELS: Final = (
	LocalModelManifest(
		name="qwen3:14b",
		runtime="ollama",
		license="Apache-2.0",
		min_memory_gb=16,
		description="默认推荐；招聘短回复质量与本地部署成本较均衡。",
		recommended=True,
	),
	LocalModelManifest(
		name="qwen3:8b",
		runtime="ollama",
		license="Apache-2.0",
		min_memory_gb=8,
		description="低配机器降级选项；建议配合人审。",
	),
	LocalModelManifest(
		name="qwen3:32b",
		runtime="ollama",
		license="Apache-2.0",
		min_memory_gb=32,
		description="高配 GPU/内存机器选项；回复质量更稳。",
	),
)


def _nonnegative_integer(value: Any, *, field: str) -> int:
	if isinstance(value, bool):
		raise LocalModelManifestError("MODEL_MANIFEST_INVALID", f"{field} must be a non-negative integer")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise LocalModelManifestError("MODEL_MANIFEST_INVALID", f"{field} must be a non-negative integer") from exc
	if not math.isfinite(number) or not number.is_integer() or number < 0:
		raise LocalModelManifestError("MODEL_MANIFEST_INVALID", f"{field} must be a non-negative integer")
	return int(number)


def _strict_bool(value: Any, *, field: str) -> bool:
	if isinstance(value, bool):
		return value
	if value in (0, 1):
		return bool(value)
	if isinstance(value, str):
		normalized = value.strip().lower()
		if normalized in {"true", "1", "yes"}:
			return True
		if normalized in {"false", "0", "no", ""}:
			return False
	raise LocalModelManifestError("MODEL_MANIFEST_INVALID", f"{field} must be a boolean")


def parse_model_manifest(raw: dict[str, Any]) -> LocalModelManifest:
	"""Parse a JSON-compatible local model manifest."""
	name = str(raw.get("name", "")).strip()
	runtime = str(raw.get("runtime", "")).strip()
	license_name = str(raw.get("license", "")).strip()
	if not name or not runtime or not license_name:
		raise LocalModelManifestError("MODEL_MANIFEST_INVALID", "manifest requires name, runtime and license")
	if runtime not in RUNTIME_BASE_URLS:
		raise LocalModelManifestError("MODEL_RUNTIME_UNSUPPORTED", f"unsupported local runtime: {runtime}")
	if license_name not in APPROVED_LOCAL_MODEL_LICENSES:
		raise LocalModelManifestError("MODEL_LICENSE_UNAPPROVED", f"license is not pre-approved: {license_name}")
	return LocalModelManifest(
		name=name,
		runtime=runtime,
		license=license_name,
		min_memory_gb=_nonnegative_integer(raw.get("min_memory_gb", 0), field="min_memory_gb"),
		description=str(raw.get("description", "")),
		recommended=_strict_bool(raw.get("recommended", False), field="recommended"),
	)


def recommended_model_rows() -> list[dict[str, Any]]:
	"""Return built-in local model manifests as JSON rows."""
	return [asdict(item) for item in RECOMMENDED_MODELS]


def model_registry_path(data_dir: Path) -> Path:
	return data_dir / "models" / "registry.json"


def read_imported_models(data_dir: Path) -> list[ImportedLocalModel]:
	path = model_registry_path(data_dir)
	if not path.exists():
		return []
	try:
		rows = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, UnicodeDecodeError, json.JSONDecodeError):
		return []
	if not isinstance(rows, list):
		return []
	return [
		ImportedLocalModel(
			model=str(row.get("model", "")),
			path=str(row.get("path", "")),
			runtime=str(row.get("runtime", "custom")),
		)
		for row in rows
		if isinstance(row, dict) and row.get("model") and row.get("path")
	]


def _write_registry(path: Path, rows: list[ImportedLocalModel]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
	try:
		temporary.write_text(
			json.dumps([asdict(item) for item in rows], ensure_ascii=False, indent=2),
			encoding="utf-8",
		)
		os.replace(temporary, path)
	finally:
		temporary.unlink(missing_ok=True)


def import_local_model(data_dir: Path, source: Path, model: str) -> ImportedLocalModel:
	"""Copy an external model artifact into the user data directory and register it."""
	if not source.exists():
		raise LocalModelManifestError("MODEL_SOURCE_NOT_FOUND", f"model source does not exist: {source}")
	model_name = model.strip()
	if not model_name or len(model_name) > 256:
		raise LocalModelManifestError("MODEL_MANIFEST_INVALID", "model name must be 1-256 characters")
	target_dir = data_dir / "models" / _safe_model_dir(model_name)
	target_dir.mkdir(parents=True, exist_ok=True)
	target = target_dir / source.name
	try:
		if source.is_dir():
			if target.exists():
				shutil.rmtree(target)
			shutil.copytree(source, target)
		else:
			shutil.copy2(source, target)
	except OSError as exc:
		raise LocalModelManifestError("MODEL_IMPORT_FAILED", f"failed to copy model source: {exc}") from exc
	imported = ImportedLocalModel(model=model_name, path=str(target), runtime="custom")
	rows = [item for item in read_imported_models(data_dir) if item.model != model_name]
	rows.append(imported)
	try:
		_write_registry(model_registry_path(data_dir), rows)
	except OSError as exc:
		raise LocalModelManifestError("MODEL_IMPORT_FAILED", f"failed to update model registry: {exc}") from exc
	return imported


def _safe_model_dir(model: str) -> str:
	return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in model).strip("-") or "model"
