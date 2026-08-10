import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from boss_agent_cli.resume.models import ResumeData, ResumeFile, dict_to_resume, resume_to_dict


def _safe_filename(name: str) -> str:
	"""将简历名称转为安全的文件名"""
	return name.replace("/", "_").replace("\\", "_").replace("\0", "_")


def _atomic_write_private(path: Path, text: str) -> None:
	"""Atomically persist sensitive resume JSON with owner-only POSIX permissions."""
	data = text.encode("utf-8")
	temporary = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
	fd: int | None = None
	try:
		fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, "wb") as handle:
			fd = None
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, path)
		try:
			path.chmod(0o600)
		except OSError:
			pass
	finally:
		if fd is not None:
			os.close(fd)
		try:
			temporary.unlink()
		except FileNotFoundError:
			pass


def _load_object(path: Path) -> dict[str, Any] | None:
	try:
		raw = json.loads(path.read_text(encoding="utf-8"))
	except (json.JSONDecodeError, OSError, UnicodeDecodeError):
		return None
	if not isinstance(raw, dict):
		return None
	try:
		path.chmod(0o600)
	except OSError:
		pass
	return cast("dict[str, Any]", raw)


class ResumeStore:
	"""简历文件存储（JSON 文件），存储路径 ~/.boss-agent/resumes/"""

	def __init__(self, resumes_dir: Path):
		self._dir = resumes_dir
		self._dir.mkdir(parents=True, exist_ok=True)

	def _path_for(self, name: str) -> Path:
		return self._dir / f"{_safe_filename(name)}.json"

	def list_all(self) -> list[dict[str, Any]]:
		"""列出所有可读取简历摘要（损坏或非对象 JSON 不进入列表）。"""
		results: list[dict[str, Any]] = []
		for path in sorted(self._dir.glob("*.json")):
			raw = _load_object(path)
			if raw is None:
				continue
			results.append({
				"name": raw.get("name", ""),
				"title": raw.get("title", ""),
				"updated_at": raw.get("updated_at", ""),
			})
		return results

	def get(self, name: str) -> ResumeData | None:
		"""按名称读取简历；损坏或非对象 JSON 按不可用记录处理。"""
		path = self._path_for(name)
		if not path.exists():
			return None
		raw = _load_object(path)
		if raw is None:
			return None
		try:
			return dict_to_resume(raw)
		except (TypeError, ValueError, KeyError, AttributeError):
			return None

	def save(self, resume: ResumeData) -> None:
		"""保存/更新简历，自动更新 updated_at，并原子替换目标 JSON。"""
		resume.updated_at = datetime.now().isoformat()
		d = resume_to_dict(resume)
		path = self._path_for(resume.name)
		_atomic_write_private(path, json.dumps(d, ensure_ascii=False, indent=2))

	def delete(self, name: str) -> bool:
		"""删除简历，返回是否成功"""
		path = self._path_for(name)
		if not path.exists():
			return False
		path.unlink()
		return True

	def exists(self, name: str) -> bool:
		"""检查简历是否存在"""
		return self._path_for(name).exists()

	def import_file(self, file_path: Path) -> ResumeData:
		"""导入 JSON 文件（兼容 wzdnzd/zine0 camelCase 格式）。"""
		raw_text = file_path.read_text(encoding="utf-8")
		loaded = json.loads(raw_text)
		if not isinstance(loaded, dict):
			raise ValueError("简历 JSON 顶层必须是对象")
		raw = cast("dict[str, Any]", loaded)

		if "version" in raw and "data" in raw:
			data = raw.get("data")
			if not isinstance(data, dict):
				raise ValueError("简历 envelope.data 必须是对象")
			raw = cast("dict[str, Any]", data)

		resume = dict_to_resume(raw)
		self.save(resume)
		return resume

	def export_json(self, name: str) -> str:
		"""导出为 ResumeFile JSON 字符串"""
		resume = self.get(name)
		if resume is None:
			raise FileNotFoundError(f"简历 '{name}' 不存在")

		from boss_agent_cli import __version__

		envelope = ResumeFile(data=resume)
		envelope.metadata["exported_at"] = datetime.now().isoformat()
		envelope.metadata["app_version"] = __version__

		d = {
			"version": envelope.version,
			"data": resume_to_dict(resume),
			"metadata": envelope.metadata,
		}
		return json.dumps(d, ensure_ascii=False, indent=2)

	def clone(self, name: str, new_name: str) -> ResumeData:
		"""复制简历为新版本"""
		resume = self.get(name)
		if resume is None:
			raise FileNotFoundError(f"简历 '{name}' 不存在")
		resume.name = new_name
		resume.created_at = ""
		resume.updated_at = ""
		resume.__post_init__()
		self.save(resume)
		return resume
