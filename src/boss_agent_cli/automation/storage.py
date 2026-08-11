"""Crash-safe file-backed automation state, queues, and event logs."""

from __future__ import annotations

import csv
import json
import math
import os
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, cast
from uuid import uuid4

from boss_agent_cli.automation.models import AutomationEvent, PendingAction, PlatformAction, ReviewItem


class AutomationStorageError(RuntimeError):
	"""Raised when authoritative automation persistence is malformed or unavailable."""


def _private_chmod(path: Path, mode: int = 0o600) -> None:
	try:
		path.chmod(mode)
	except OSError:
		pass


def _atomic_write(path: Path, data: bytes) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
	fd: int | None = None
	try:
		fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		with os.fdopen(fd, "wb") as handle:
			fd = None
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(temporary, path)
		_private_chmod(path)
	finally:
		if fd is not None:
			os.close(fd)
		try:
			temporary.unlink(missing_ok=True)
		except OSError:
			pass


def _acquire_file_lock(fd: int) -> Callable[[], None]:
	if os.name == "nt":
		import msvcrt

		if os.fstat(fd).st_size < 1:
			os.ftruncate(fd, 1)
		os.lseek(fd, 0, os.SEEK_SET)
		try:
			msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
		except OSError as exc:
			raise AutomationStorageError("automation 存储锁获取失败") from exc

		def release_windows() -> None:
			os.lseek(fd, 0, os.SEEK_SET)
			msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

		return release_windows

	import fcntl

	fcntl.flock(fd, fcntl.LOCK_EX)

	def release_posix() -> None:
		fcntl.flock(fd, fcntl.LOCK_UN)

	return release_posix


def _model_row(item: Any) -> dict[str, Any]:
	row = asdict(item)
	action = row.get("action")
	if isinstance(action, PlatformAction):
		row["action"] = action.value
	return row


def _safe_csv_cell(value: str) -> str:
	return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def _finite_unit(value: Any, *, label: str) -> float:
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise AutomationStorageError(f"{label} 必须是 0-1 的有限数字") from exc
	if not math.isfinite(number) or not 0 <= number <= 1:
		raise AutomationStorageError(f"{label} 必须是 0-1 的有限数字")
	return number


class AutomationStore:
	"""File-backed recruiter automation store with atomic authoritative writes."""

	def __init__(self, data_dir: Path) -> None:
		self.root = data_dir / "automation"
		self.root.mkdir(parents=True, exist_ok=True)
		(self.root / "archive").mkdir(exist_ok=True)
		_private_chmod(self.root, 0o700)
		_private_chmod(self.root / "archive", 0o700)
		self._approval_tx_path = self.root / ".approval-transaction.json"
		self._lock_path = self.root / ".store.lock"

	@property
	def state_path(self) -> Path:
		return self.root / "state.json"

	@property
	def review_path(self) -> Path:
		return self.root / "human-review-queue.jsonl"

	@property
	def pending_path(self) -> Path:
		return self.root / "pending-actions.jsonl"

	@contextmanager
	def _locked(self) -> Iterator[None]:
		fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
		release: Callable[[], None] | None = None
		try:
			release = _acquire_file_lock(fd)
			_private_chmod(self._lock_path)
			yield
		finally:
			if release is not None:
				try:
					release()
				except OSError:
					pass
			os.close(fd)

	@staticmethod
	def _default_state() -> dict[str, Any]:
		return {"conversations": {}, "autonomy": {}, "safety": {}}

	@staticmethod
	def _validate_state(payload: Any) -> dict[str, Any]:
		if not isinstance(payload, dict):
			raise AutomationStorageError("state.json 损坏：顶层必须是对象")
		state = cast("dict[str, Any]", payload)
		for key in ("conversations", "autonomy", "safety"):
			value = state.get(key, {})
			if not isinstance(value, dict):
				raise AutomationStorageError(f"state.json 损坏：{key} 必须是对象")
			state[key] = value
		return state

	def _read_state_unlocked(self) -> dict[str, Any]:
		if not self.state_path.exists():
			return self._default_state()
		try:
			payload = json.loads(self.state_path.read_text(encoding="utf-8"))
		except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise AutomationStorageError("state.json 损坏，automation 已安全停止") from exc
		return self._validate_state(payload)

	def read_state(self) -> dict[str, Any]:
		with self._locked():
			return self._read_state_unlocked()

	def _write_state_unlocked(self, state: dict[str, Any]) -> None:
		validated = self._validate_state(state)
		_atomic_write(
			self.state_path,
			(json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
		)

	def write_state(self, state: dict[str, Any]) -> None:
		with self._locked():
			self._write_state_unlocked(state)

	def append_event(self, event: AutomationEvent) -> None:
		with self._locked():
			self._append_jsonl_unlocked("action-log.jsonl", _model_row(event))

	def append_review(self, item: ReviewItem) -> None:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			rows = self._read_jsonl_unlocked(self.review_path.name)
			rows.append(_model_row(item))
			self._write_jsonl_unlocked(self.review_path.name, rows)

	def append_pending(self, action: PendingAction) -> None:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			rows = self._read_jsonl_unlocked(self.pending_path.name)
			if not any(str(row.get("id")) == action.id for row in rows):
				rows.append(_model_row(action))
				self._write_jsonl_unlocked(self.pending_path.name, rows)

	def read_reviews(self) -> list[ReviewItem]:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			return [_review_from_row(row) for row in self._read_jsonl_unlocked(self.review_path.name)]

	def read_pending(self) -> list[PendingAction]:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			return [_pending_from_row(row) for row in self._read_jsonl_unlocked(self.pending_path.name)]

	def write_reviews(self, items: list[ReviewItem]) -> None:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			self._write_jsonl_unlocked(self.review_path.name, [_model_row(item) for item in items])

	def write_pending(self, items: list[PendingAction]) -> None:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			self._write_jsonl_unlocked(self.pending_path.name, [_model_row(item) for item in items])

	def approve_review(self, review_id: str, reviewed_at: str) -> PendingAction | None:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			reviews = [_review_from_row(row) for row in self._read_jsonl_unlocked(self.review_path.name)]
			pending_rows = self._read_jsonl_unlocked(self.pending_path.name)
			updated_reviews: list[ReviewItem] = []
			pending: PendingAction | None = None
			for item in reviews:
				if item.id == review_id and item.status == "review":
					item.status = "approved"
					item.reviewed_at = reviewed_at
					pending = PendingAction(
						id=item.id,
						candidate_key=item.candidate_key,
						platform=item.platform,
						action=item.action,
						message=item.message,
						payload=dict(item.payload),
						approved_review_id=item.id,
						status="pending",
						created_at=reviewed_at,
						confidence=item.confidence,
						reason=item.reason,
						decision_score=item.decision_score,
					)
				updated_reviews.append(item)
				else:
					updated_reviews.append(item)
			if pending is None:
				return None
			transaction = {
				"reviews": [_model_row(item) for item in updated_reviews],
				"pending_action": _model_row(pending),
			}
			_atomic_write(
				self._approval_tx_path,
				(json.dumps(transaction, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
			)
			self._write_jsonl_unlocked(self.review_path.name, cast("list[dict[str, Any]]", transaction["reviews"]))
			if not any(str(row.get("id")) == pending.id for row in pending_rows):
				pending_rows.append(cast("dict[str, Any]", transaction["pending_action"]))
				self._write_jsonl_unlocked(self.pending_path.name, pending_rows)
			self._approval_tx_path.unlink(missing_ok=True)
			return pending

	def reject_review(self, review_id: str, reason: str, reviewed_at: str) -> ReviewItem | None:
		with self._locked():
			self._recover_approval_transaction_unlocked()
			reviews = [_review_from_row(row) for row in self._read_jsonl_unlocked(self.review_path.name)]
			rejected: ReviewItem | None = None
			for item in reviews:
				if item.id == review_id and item.status == "review":
					item.status = "rejected"
					item.reviewed_at = reviewed_at
					item.rejection_reason = reason
					rejected = item
			if rejected is not None:
				self._write_jsonl_unlocked(self.review_path.name, [_model_row(item) for item in reviews])
			return rejected

	def _recover_approval_transaction_unlocked(self) -> None:
		if not self._approval_tx_path.exists():
			return
		try:
			payload = json.loads(self._approval_tx_path.read_text(encoding="utf-8"))
		except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise AutomationStorageError("approval transaction 损坏，automation 已安全停止") from exc
		if not isinstance(payload, dict):
			raise AutomationStorageError("approval transaction 损坏，automation 已安全停止")
		review_rows = payload.get("reviews")
		pending_raw = payload.get("pending_action")
		if not isinstance(review_rows, list) or any(not isinstance(row, dict) for row in review_rows):
			raise AutomationStorageError("approval transaction reviews 损坏")
		if not isinstance(pending_raw, dict):
			raise AutomationStorageError("approval transaction pending_action 损坏")
		validated_reviews = [
			_model_row(_review_from_row(cast("dict[str, Any]", row)))
			for row in review_rows
		]
		pending = _pending_from_row(cast("dict[str, Any]", pending_raw))
		pending_row = _model_row(pending)
		self._write_jsonl_unlocked(self.review_path.name, validated_reviews)
		pending_rows = self._read_jsonl_unlocked(self.pending_path.name)
		if not any(str(row.get("id")) == pending.id for row in pending_rows):
			pending_rows.append(pending_row)
			self._write_jsonl_unlocked(self.pending_path.name, pending_rows)
		self._approval_tx_path.unlink(missing_ok=True)

	def read_jsonl(self, name: str) -> list[dict[str, Any]]:
		with self._locked():
			return self._read_jsonl_unlocked(name)

	def _read_jsonl_unlocked(self, name: str) -> list[dict[str, Any]]:
		path = self.root / name
		if not path.exists():
			return []
		try:
			lines = path.read_text(encoding="utf-8").splitlines()
		except (OSError, UnicodeDecodeError) as exc:
			raise AutomationStorageError(f"{name} 读取失败") from exc
		rows: list[dict[str, Any]] = []
		for line_number, line in enumerate(lines, 1):
			if not line.strip():
				continue
			try:
				parsed = json.loads(line)
			except json.JSONDecodeError as exc:
				raise AutomationStorageError(f"{name} 第 {line_number} 行 JSON 损坏") from exc
			if not isinstance(parsed, dict):
				raise AutomationStorageError(f"{name} 第 {line_number} 行必须是对象")
			rows.append(cast("dict[str, Any]", parsed))
		return rows

	def write_jsonl(self, name: str, rows: list[dict[str, Any]]) -> None:
		with self._locked():
			self._write_jsonl_unlocked(name, rows)

	def _write_jsonl_unlocked(self, name: str, rows: list[dict[str, Any]]) -> None:
		if any(not isinstance(row, dict) for row in rows):
			raise AutomationStorageError(f"{name} 只能写入对象行")
		body = "".join(f"{json.dumps(row, ensure_ascii=False, sort_keys=True)}\n" for row in rows)
		_atomic_write(self.root / name, body.encode("utf-8"))

	def append_interview_lead(self, candidate_key: str, interview_time: str, reason: str) -> None:
		path = self.root / "interview-leads.csv"
		with self._locked():
			new_file = not path.exists()
			with path.open("a", encoding="utf-8", newline="") as handle:
				writer = csv.writer(handle)
				if new_file:
					writer.writerow(["candidate_key", "interview_time", "reason"])
				writer.writerow([
					_safe_csv_cell(str(candidate_key)),
					_safe_csv_cell(str(interview_time)),
					_safe_csv_cell(str(reason)),
				])
				handle.flush()
				os.fsync(handle.fileno())
			_private_chmod(path)

	def stats(self) -> dict[str, Any]:
		events = self.read_jsonl("action-log.jsonl")
		reviews = self.read_jsonl(self.review_path.name)
		pending = self.read_jsonl(self.pending_path.name)
		state = self.read_state()
		today = datetime.now(timezone.utc).date().isoformat()
		recent_errors = [item for item in events[-20:] if item.get("status") in {"STOPPED_BY_SAFETY", "CIRCUIT_BREAKER_OPEN"}]
		return {
			"events": len(events),
			"auto_executed": sum(1 for item in events if item.get("status") == "AUTO_EXECUTED"),
			"dry_run": sum(1 for item in events if item.get("status") == "DRY_RUN"),
			"today_executed": sum(
				1 for item in events
				if str(item.get("ts", "")).startswith(today) and item.get("status") == "AUTO_EXECUTED"
			),
			"human_reviews": sum(1 for item in reviews if item.get("status") == "review"),
			"pending_actions": sum(1 for item in pending if item.get("status") == "pending"),
			"circuit_breakers": sum(1 for item in events if item.get("status") == "CIRCUIT_BREAKER_OPEN"),
			"circuit_breaker": state.get("autonomy", {}).get("circuit_breaker", {}),
			"recent_errors": recent_errors[-5:],
		}

	def _append_jsonl_unlocked(self, name: str, row: dict[str, Any]) -> None:
		path = self.root / name
		with path.open("a", encoding="utf-8") as handle:
			handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
			handle.write("\n")
			handle.flush()
			os.fsync(handle.fileno())
		_private_chmod(path)


def _review_from_row(row: dict[str, Any]) -> ReviewItem:
	try:
		action = PlatformAction(row.get("action", ""))
	except ValueError as exc:
		raise AutomationStorageError(f"review action 无效: {row.get('action')!r}") from exc
	confidence = _finite_unit(row.get("confidence", 0.0), label="review confidence")
	decision_score = _finite_unit(row.get("decision_score", confidence), label="review decision_score")
	payload = row.get("payload", {})
	if not isinstance(payload, dict):
		raise AutomationStorageError("review payload 必须是对象")
	return ReviewItem(
		id=str(row.get("id", "")),
		candidate_key=str(row.get("candidate_key", "")),
		platform=str(row.get("platform", "")),
		action=action,
		message=str(row.get("message", "")),
		reason=str(row.get("reason", "")),
		decision_score=decision_score,
		confidence=confidence,
		payload=cast("dict[str, Any]", payload),
		status=str(row.get("status", "review")),
		created_at=str(row.get("created_at") or row.get("ts") or ""),
		ts=str(row.get("ts") or row.get("created_at") or ""),
		reviewed_at=str(row.get("reviewed_at", "")),
		rejection_reason=str(row.get("rejection_reason", "")),
	)


def _pending_from_row(row: dict[str, Any]) -> PendingAction:
	try:
		action = PlatformAction(row.get("action", ""))
	except ValueError as exc:
		raise AutomationStorageError(f"pending action 无效: {row.get('action')!r}") from exc
	confidence = _finite_unit(row.get("confidence", 0.0), label="pending confidence")
	decision_score = _finite_unit(row.get("decision_score", confidence), label="pending decision_score")
	payload = row.get("payload", {})
	if not isinstance(payload, dict):
		raise AutomationStorageError("pending payload 必须是对象")
	return PendingAction(
		id=str(row.get("id", "")),
		candidate_key=str(row.get("candidate_key", "")),
		platform=str(row.get("platform", "")),
		action=action,
		message=str(row.get("message", "")),
		payload=cast("dict[str, Any]", payload),
		approved_review_id=str(row.get("approved_review_id", "")),
		status=str(row.get("status", "pending")),
		created_at=str(row.get("created_at") or row.get("ts") or ""),
		ts=str(row.get("ts") or row.get("created_at") or ""),
		confidence=confidence,
		reason=str(row.get("reason", "")),
		decision_score=decision_score,
		updated_at=str(row.get("updated_at", "")),
	)
