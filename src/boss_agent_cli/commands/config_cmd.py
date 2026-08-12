"""boss config — 查看和修改配置项。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import click

from boss_agent_cli.config import (
	ConfigLockBusy,
	DEFAULTS,
	read_user_config,
	replace_user_config,
	update_user_config,
)
from boss_agent_cli.display import handle_output, render_simple_list
from boss_agent_cli.output import emit_error

_CONFIG_CHOICES = {
	"operating_mode": ("assisted", "research"),
	"log_level": ("debug", "info", "warning", "error"),
	"role": ("candidate", "recruiter"),
}
_PUBLIC_CONFIG_KEYS = tuple(key for key in DEFAULTS if key != "low_risk_mode")
_AVAILABLE_CONFIG_MESSAGE = f"可用项: {', '.join(sorted(_PUBLIC_CONFIG_KEYS))}"


def _exit_error(ctx: click.Context, *, code: str, message: str) -> None:
	emit_error("config", code=code, message=message)
	ctx.exit(1)


def _update_config_or_exit(
	ctx: click.Context,
	config_path: Path,
	*,
	updates: dict[str, Any] | None = None,
	removals: tuple[str, ...] = (),
) -> None:
	try:
		update_user_config(config_path, updates=updates, removals=removals)
	except ConfigLockBusy as exc:
		_exit_error(ctx, code="CONFIG_BUSY", message=str(exc))
	except OSError as exc:
		_exit_error(ctx, code="CONFIG_WRITE_FAILED", message=f"配置保存失败: {exc}")


@click.group("config", invoke_without_command=True)
@click.pass_context
def config_group(ctx: click.Context) -> None:
	"""查看和修改配置项。不带子命令时显示当前全部配置。"""
	if ctx.invoked_subcommand is None:
		ctx.invoke(config_list_cmd)


@config_group.command("list")
@click.pass_context
def config_list_cmd(ctx: click.Context) -> None:
	"""显示当前全部配置。"""
	cfg = ctx.obj["config"]
	config_path = ctx.obj["data_dir"] / "config.json"
	user_overrides = _load_user_overrides(config_path)

	items = []
	for key in sorted(_PUBLIC_CONFIG_KEYS):
		default_val = DEFAULTS[key]
		current_val = cfg.get(key, default_val)
		is_custom = key in user_overrides
		items.append({
			"key": key,
			"value": current_val,
			"default": default_val,
			"source": "用户配置" if is_custom else "默认值",
		})

	data = {"config_path": str(config_path), "items": items}
	hints = {
		"next_actions": [
			"boss config set <键> <值> — 修改配置项",
			"boss config get <键> — 查看单个配置项",
			"boss config reset <键> — 恢复默认值",
		],
	}
	handle_output(
		ctx,
		"config",
		data,
		render=lambda d: render_simple_list(
			d["items"],
			f"配置 ({d['config_path']})",
			[
				("key", "key", "cyan"),
				("value", "value", "green"),
				("source", "source", "dim"),
			],
		),
		hints=hints,
	)


@config_group.command("get")
@click.argument("key")
@click.pass_context
def config_get_cmd(ctx: click.Context, key: str) -> None:
	"""查看单个配置项的值。"""
	cfg = ctx.obj["config"]
	if key not in _PUBLIC_CONFIG_KEYS:
		_exit_error(ctx, code="INVALID_PARAM", message=f"未知配置项。{_AVAILABLE_CONFIG_MESSAGE}")
		return

	data = {
		"key": key,
		"value": cfg.get(key, DEFAULTS[key]),
		"default": DEFAULTS[key],
	}
	handle_output(ctx, "config", data, render=lambda d: None)


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set_cmd(ctx: click.Context, key: str, value: str) -> None:
	"""修改配置项。"""
	if key not in _PUBLIC_CONFIG_KEYS:
		_exit_error(ctx, code="INVALID_PARAM", message=f"未知配置项。{_AVAILABLE_CONFIG_MESSAGE}")
		return

	try:
		parsed_value = _parse_value(value, DEFAULTS[key])
		_validate_value(key, parsed_value)
	except (TypeError, ValueError, json.JSONDecodeError) as exc:
		_exit_error(ctx, code="INVALID_PARAM", message=f"{key} 配置值无效: {exc}")
		return

	choices = _CONFIG_CHOICES.get(key)
	if choices is not None and parsed_value not in choices:
		_exit_error(ctx, code="INVALID_PARAM", message=f"{key} 必须是以下值之一: {', '.join(choices)}")
		return

	config_path = ctx.obj["data_dir"] / "config.json"
	removals = ("low_risk_mode",) if key == "operating_mode" else ()
	_update_config_or_exit(ctx, config_path, updates={key: parsed_value}, removals=removals)

	data = {"key": key, "value": parsed_value, "previous": ctx.obj["config"].get(key)}
	handle_output(ctx, "config", data, render=lambda d: None)


@config_group.command("reset")
@click.argument("key")
@click.pass_context
def config_reset_cmd(ctx: click.Context, key: str) -> None:
	"""将配置项恢复为默认值。"""
	if key not in _PUBLIC_CONFIG_KEYS:
		_exit_error(ctx, code="INVALID_PARAM", message=f"未知配置项。{_AVAILABLE_CONFIG_MESSAGE}")
		return

	config_path = ctx.obj["data_dir"] / "config.json"
	_update_config_or_exit(ctx, config_path, removals=(key,))

	data = {"key": key, "value": DEFAULTS[key], "restored": True}
	handle_output(ctx, "config", data, render=lambda d: None)


def _load_user_overrides(config_path: Path) -> dict[str, Any]:
	"""加载用户自定义配置（不含默认值）。"""
	return read_user_config(config_path)


def _save_user_overrides(config_path: Path, user_cfg: dict[str, Any]) -> None:
	"""原子保存完整用户配置；常规 set/reset 应优先使用 update_user_config。"""
	replace_user_config(config_path, user_cfg)


def _parse_value(raw: str, default: Any) -> Any:
	"""根据默认值类型推断并转换输入值，拒绝模糊类型转换。"""
	if default is None:
		if raw.lower() in ("null", "none", ""):
			return None
		return raw
	if isinstance(default, bool):
		boolean_value = raw.strip().lower()
		if boolean_value in ("true", "1", "yes"):
			return True
		if boolean_value in ("false", "0", "no"):
			return False
		raise ValueError("布尔值必须是 true/false、1/0 或 yes/no")
	if isinstance(default, int):
		return int(raw)
	if isinstance(default, float):
		numeric_value = float(raw)
		if not math.isfinite(numeric_value):
			raise ValueError("数字必须是有限值")
		return numeric_value
	if isinstance(default, list):
		parts = [part.strip() for part in raw.split(",")]
		if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in default):
			values = [float(part) for part in parts]
			if any(not math.isfinite(item) for item in values):
				raise ValueError("列表数字必须是有限值")
			return values
		return parts
	if isinstance(default, dict):
		parsed = json.loads(raw)
		if not isinstance(parsed, dict):
			raise ValueError("必须提供 JSON object")
		return parsed
	return raw


def _validate_value(key: str, value: Any) -> None:
	if key in {"request_delay", "batch_greet_delay"}:
		if not isinstance(value, list) or len(value) != 2:
			raise ValueError("必须提供两个逗号分隔的非负数字")
		if any(isinstance(item, bool) or not isinstance(item, (int, float)) or item < 0 for item in value):
			raise ValueError("延迟必须是非负数字")
		if float(value[0]) > float(value[1]):
			raise ValueError("最小延迟不能大于最大延迟")
	if key in {"automation", "crawl"} and not isinstance(value, dict):
		raise ValueError("必须提供 JSON object")
