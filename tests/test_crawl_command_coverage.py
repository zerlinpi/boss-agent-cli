import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
from click.testing import CliRunner

from boss_agent_cli.commands import crawl
from boss_agent_cli.config import DEFAULTS
from boss_agent_cli.crawler.service import CrawlSettings
from boss_agent_cli.main import cli


def _ctx(tmp_path: Path, *, config: dict[str, Any] | None = None) -> click.Context:
	return click.Context(
		crawl.crawl_group,
		obj={
			"data_dir": tmp_path,
			"config": config or {},
			"json_output": True,
		},
	)


def _invoke(tmp_path: Path, *args: str):
	return CliRunner().invoke(
		cli,
		["--data-dir", str(tmp_path), "--json", "crawl", *args],
	)


def test_crawl_config_merges_defaults_only_for_mapping(tmp_path):
	ctx = _ctx(tmp_path, config={"crawl": {"max_requests": 7}})
	merged = crawl._crawl_config(ctx)
	assert merged["max_requests"] == 7
	assert "max_seconds" in merged

	ctx = _ctx(tmp_path, config={"crawl": "broken"})
	assert crawl._crawl_config(ctx) == dict(DEFAULTS["crawl"])


def test_save_crawl_config_recovers_invalid_files_and_preserves_unrelated_keys(tmp_path):
	config_path = tmp_path / "config.json"
	config_path.write_text("{not-json", encoding="utf-8")
	assert crawl._save_crawl_config(tmp_path, {"max_requests": 11, "chrome_path": None}) == {
		"max_requests": 11,
	}

	config_path.write_text(
		json.dumps({"role": "candidate", "crawl": ["broken"]}),
		encoding="utf-8",
	)
	updated = crawl._save_crawl_config(tmp_path, {"max_seconds": 120})
	assert updated == {"max_seconds": 120}
	persisted = json.loads(config_path.read_text(encoding="utf-8"))
	assert persisted["role"] == "candidate"
	assert persisted["crawl"] == {"max_seconds": 120}


def test_city_code_accepts_names_and_numeric_codes():
	assert crawl._city_code("杭州") == "101210100"
	assert crawl._city_code("101210100") == "101210100"
	try:
		crawl._city_code("不存在的城市")
	except ValueError as exc:
		assert "city 必须" in str(exc)
	else:
		raise AssertionError("expected invalid city to fail")


def test_require_crawl_capabilities_stops_at_each_policy_gate(tmp_path, monkeypatch):
	ctx = _ctx(tmp_path)
	calls: list[str] = []

	def deny_crawl(_ctx, capability: str) -> bool:
		calls.append(capability)
		return False

	monkeypatch.setattr(crawl, "require_compliance_allowed", deny_crawl)
	assert crawl._require_crawl_capabilities(ctx) is False
	assert calls == ["crawl"]

	calls.clear()
	monkeypatch.setattr(
		crawl,
		"require_compliance_allowed",
		lambda _ctx, capability: calls.append(capability) is None and capability != "crawl-cdp",
	)
	assert crawl._require_crawl_capabilities(ctx) is False
	assert calls == ["crawl", "crawl-cdp"]

	calls.clear()
	monkeypatch.setattr(
		crawl,
		"require_compliance_allowed",
		lambda _ctx, capability: calls.append(capability) is None and capability != "crawl-hook",
	)
	assert crawl._require_crawl_capabilities(ctx, "screenshot-full") is False
	assert calls == ["crawl", "crawl-cdp", "crawl-hook"]

	calls.clear()
	monkeypatch.setattr(
		crawl,
		"require_compliance_allowed",
		lambda _ctx, capability: calls.append(capability) is None or True,
	)
	assert crawl._require_crawl_capabilities(ctx, "none") is True
	assert calls == ["crawl", "crawl-cdp"]


def test_settings_from_context_uses_config_overrides_and_private_profile(tmp_path, monkeypatch):
	ctx = _ctx(
		tmp_path,
		config={
			"crawl": {
				"chrome_path": "configured-chrome",
				"cdp_port": 9333,
				"max_requests": 9,
				"max_details": 8,
				"max_seconds": 70,
				"max_retries": 2,
			}
		},
	)
	monkeypatch.setattr(crawl, "operating_mode", lambda _ctx: "research")
	settings = crawl._settings_from_context(
		ctx,
		query="AI",
		city="杭州",
		pages=3,
		with_detail=True,
		hook_profile="screenshot-full",
		hook_dir=str(tmp_path / "hooks"),
		profile_path="ignored-user-profile",
		chrome_path="override-chrome",
		cdp_port=9444,
	)
	assert settings == CrawlSettings(
		query="AI",
		city_code="101210100",
		pages=3,
		with_detail=True,
		profile_path=tmp_path / "crawl" / "chrome-profile",
		chrome_path="override-chrome",
		cdp_port=9444,
		hook_profile="screenshot-full",
		hook_dir=tmp_path / "hooks",
		max_requests=9,
		max_details=8,
		max_seconds=70,
		max_retries=2,
		operating_mode="research",
	)


def test_settings_rejects_unknown_hook_profile(tmp_path):
	ctx = _ctx(tmp_path)
	try:
		crawl._settings_from_context(
			ctx,
			query="AI",
			city="杭州",
			pages=1,
			with_detail=False,
			hook_profile="unknown",
			hook_dir=None,
			profile_path=None,
			chrome_path=None,
			cdp_port=9222,
		)
	except ValueError as exc:
		assert "unknown hook profile" in str(exc)
	else:
		raise AssertionError("expected invalid hook profile to fail")


def test_unused_local_port_and_transport_factory(tmp_path, monkeypatch):
	port = crawl._unused_local_port()
	assert 1 <= port <= 65535

	captured: dict[str, Any] = {}

	class Session:
		def __init__(self, **kwargs: Any) -> None:
			captured.update(kwargs)

	monkeypatch.setattr(crawl, "DrissionCrawlerSession", Session)
	settings = CrawlSettings(
		query="AI",
		city_code="101210100",
		pages=1,
		with_detail=False,
		profile_path=tmp_path / "profile",
		chrome_path="chrome",
		cdp_port=9333,
		hook_profile="none",
		hook_dir=None,
		operating_mode="research",
	)
	assert isinstance(crawl._transport_factory(settings), Session)
	assert captured == {
		"profile_path": tmp_path / "profile",
		"chrome_path": "chrome",
		"cdp_port": 9333,
		"hook_profile": "none",
		"hook_dir": None,
	}


def test_run_service_success_and_error_contracts(tmp_path, monkeypatch):
	ctx = _ctx(tmp_path)
	outputs: list[tuple[dict[str, Any], dict[str, Any]]] = []
	errors: list[dict[str, Any]] = []

	class Cache:
		def __init__(self, path: Path) -> None:
			self.path = path

		def __enter__(self):
			return self

		def __exit__(self, *args: Any) -> None:
			return None

	class Service:
		def __init__(self, *args: Any, **kwargs: Any) -> None:
			pass

	monkeypatch.setattr(crawl, "CacheStore", Cache)
	monkeypatch.setattr(crawl, "CrawlService", Service)
	monkeypatch.setattr(
		crawl,
		"handle_output",
		lambda _ctx, _command, data, **kwargs: outputs.append((data, kwargs)),
	)
	monkeypatch.setattr(
		crawl,
		"handle_error_output",
		lambda _ctx, _command, **kwargs: errors.append(kwargs),
	)

	completed = SimpleNamespace(run_id="run-1", status="completed", as_dict=lambda: {"status": "completed"})
	crawl._run_service(ctx, lambda service: completed)
	assert outputs[-1][0] == {"status": "completed"}
	assert "output_paths" in outputs[-1][1]["hints"]["next_actions"][0]

	stopped = SimpleNamespace(run_id="run-2", status="stopped", as_dict=lambda: {"status": "stopped"})
	crawl._run_service(ctx, lambda service: stopped)
	assert outputs[-1][1]["hints"]["next_actions"] == ["boss crawl resume run-2"]

	for exc, code in (
		(KeyError("missing"), "JOB_NOT_FOUND"),
		(ValueError("bad value"), "INVALID_PARAM"),
		(RuntimeError("browser missing"), "CRAWL_UNAVAILABLE"),
	):
		crawl._run_service(ctx, lambda service, exc=exc: (_ for _ in ()).throw(exc))
		assert errors[-1]["code"] == code


def test_launch_background_resume_builds_fixed_command(tmp_path, monkeypatch):
	captured: dict[str, Any] = {}

	def popen(command, **kwargs):
		captured["command"] = command
		captured["kwargs"] = kwargs
		return SimpleNamespace(pid=123)

	monkeypatch.setattr(crawl.subprocess, "Popen", popen)
	crawl._launch_background_resume(tmp_path, "run-1", pages=4, with_detail=True)
	command = captured["command"]
	assert command[:3] == [crawl.sys.executable, "-c", "from boss_agent_cli.main import cli; cli()"]
	assert command[-5:] == ["--from-queue", "--pages", "4", "--with-detail"][-5:]
	assert "run-1" in command
	assert captured["kwargs"]["stdin"] is crawl.subprocess.DEVNULL
	assert captured["kwargs"]["stdout"] is crawl.subprocess.DEVNULL
	assert captured["kwargs"]["stderr"] is crawl.subprocess.DEVNULL


def test_configure_command_requires_value_and_persists_updates(tmp_path):
	missing = _invoke(tmp_path, "configure")
	assert missing.exit_code == 1
	assert json.loads(missing.output)["error"]["code"] == "INVALID_PARAM"

	configured = _invoke(
		tmp_path,
		"configure",
		"--port",
		"9444",
		"--max-requests",
		"12",
		"--max-details",
		"13",
		"--max-seconds",
		"90",
		"--max-retries",
		"0",
	)
	assert configured.exit_code == 0, configured.output
	data = json.loads(configured.output)["data"]["crawl"]
	assert data == {
		"cdp_port": 9444,
		"max_requests": 12,
		"max_details": 13,
		"max_seconds": 90,
		"max_retries": 0,
	}


def test_run_command_reports_invalid_city_without_starting_service(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "_require_crawl_capabilities", lambda ctx, hook_profile=None: True)
	called = False

	def fail_if_called(*args: Any, **kwargs: Any) -> None:
		nonlocal called
		called = True

	monkeypatch.setattr(crawl, "_run_service", fail_if_called)
	result = _invoke(tmp_path, "run", "AI", "--city", "不存在")
	assert result.exit_code == 1
	assert json.loads(result.output)["error"]["code"] == "INVALID_PARAM"
	assert called is False


def test_run_command_builds_settings_and_dispatches_service(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "_require_crawl_capabilities", lambda ctx, hook_profile=None: True)
	seen: dict[str, Any] = {}

	class Service:
		def create_and_run(self, settings: CrawlSettings):
			seen["settings"] = settings
			return SimpleNamespace(run_id="run-1", status="completed", as_dict=lambda: {})

	def run_service(ctx, service_call):
		service_call(Service())

	monkeypatch.setattr(crawl, "_run_service", run_service)
	result = _invoke(
		tmp_path,
		"run",
		"AI",
		"--city",
		"杭州",
		"--pages",
		"2",
		"--with-detail",
		"--port",
		"9444",
	)
	assert result.exit_code == 0, result.output
	settings = seen["settings"]
	assert settings.city_code == "101210100"
	assert settings.pages == 2
	assert settings.with_detail is True
	assert settings.cdp_port == 9444


def test_start_command_handles_invalid_city(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "_require_crawl_capabilities", lambda ctx, hook_profile=None: True)
	result = _invoke(tmp_path, "start", "AI", "--city", "不存在")
	assert result.exit_code == 1
	assert json.loads(result.output)["error"]["code"] == "INVALID_PARAM"


def test_start_command_marks_created_run_stopped_when_background_launch_fails(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "_require_crawl_capabilities", lambda ctx, hook_profile=None: True)
	monkeypatch.setattr(
		crawl,
		"_launch_background_resume",
		lambda *args, **kwargs: (_ for _ in ()).throw(OSError("spawn failed")),
	)
	result = _invoke(tmp_path, "start", "AI", "--city", "杭州")
	assert result.exit_code == 1, result.output
	payload = json.loads(result.output)
	assert payload["error"]["code"] == "CRAWL_UNAVAILABLE"

	from boss_agent_cli.cache.store import CacheStore

	with CacheStore(tmp_path / "cache" / "boss_agent.db") as cache:
		runs = cache.list_crawl_runs(limit=10)
		assert len(runs) == 1
		assert runs[0]["status"] == "stopped"
		assert "spawn failed" in str(runs[0]["error"])


def _fake_cache_factory(run: dict[str, Any] | None = None, *, stop_result: bool = True):
	class Cache:
		def __init__(self, path: Path) -> None:
			self.path = path

		def __enter__(self):
			return self

		def __exit__(self, *args: Any) -> None:
			return None

		def get_crawl_run(self, run_id: str):
			return run

		def request_crawl_stop(self, run_id: str) -> bool:
			return stop_result

	return Cache


def test_resume_background_not_found_and_existing_running_run(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "_require_crawl_capabilities", lambda ctx, hook_profile=None: True)
	monkeypatch.setattr(crawl, "CacheStore", _fake_cache_factory(None))
	missing = _invoke(tmp_path, "resume", "missing", "--background")
	assert missing.exit_code == 1
	assert json.loads(missing.output)["error"]["code"] == "JOB_NOT_FOUND"

	launched: list[str] = []
	monkeypatch.setattr(crawl, "CacheStore", _fake_cache_factory({"status": "running"}))
	monkeypatch.setattr(crawl, "_launch_background_resume", lambda data_dir, run_id, **kwargs: launched.append(run_id))
	running = _invoke(tmp_path, "resume", "run-1", "--background")
	assert running.exit_code == 0, running.output
	assert json.loads(running.output)["data"]["status"] == "running"
	assert launched == []


def test_resume_background_launches_stopped_run_and_maps_spawn_error(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "_require_crawl_capabilities", lambda ctx, hook_profile=None: True)
	monkeypatch.setattr(crawl, "CacheStore", _fake_cache_factory({"status": "stopped"}))
	launches: list[tuple[str, dict[str, Any]]] = []
	monkeypatch.setattr(
		crawl,
		"_launch_background_resume",
		lambda data_dir, run_id, **kwargs: launches.append((run_id, kwargs)),
	)
	result = _invoke(tmp_path, "resume", "run-1", "--background", "--pages", "3", "--with-detail")
	assert result.exit_code == 0, result.output
	assert launches == [("run-1", {"pages": 3, "with_detail": True})]
	assert json.loads(result.output)["data"]["status"] == "queued"

	monkeypatch.setattr(
		crawl,
		"_launch_background_resume",
		lambda *args, **kwargs: (_ for _ in ()).throw(OSError("spawn failed")),
	)
	failed = _invoke(tmp_path, "resume", "run-1", "--background")
	assert failed.exit_code == 1
	assert json.loads(failed.output)["error"]["code"] == "CRAWL_UNAVAILABLE"


def test_resume_foreground_dispatches_service_with_clear_stop_semantics(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "_require_crawl_capabilities", lambda ctx, hook_profile=None: True)
	seen: list[dict[str, Any]] = []

	class Service:
		def resume(self, run_id: str, **kwargs: Any):
			seen.append({"run_id": run_id, **kwargs})
			return SimpleNamespace(run_id=run_id, status="completed", as_dict=lambda: {})

	monkeypatch.setattr(crawl, "_run_service", lambda ctx, service_call: service_call(Service()))
	result = _invoke(tmp_path, "resume", "run-1", "--pages", "2", "--with-detail")
	assert result.exit_code == 0, result.output
	assert seen[-1]["clear_stop"] is True
	assert seen[-1]["pages"] == 2
	assert seen[-1]["with_detail"] is True

	queued = _invoke(tmp_path, "resume", "run-1", "--from-queue")
	assert queued.exit_code == 0, queued.output
	assert seen[-1]["clear_stop"] is False


def test_status_stop_and_results_commands_cover_success_and_missing(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "CacheStore", _fake_cache_factory({"status": "completed"}, stop_result=True))
	monkeypatch.setattr(crawl, "crawl_status", lambda cache, run_id: {"run_id": run_id, "status": "completed"})
	monkeypatch.setattr(
		crawl,
		"crawl_results",
		lambda cache, run_id, **kwargs: {"run_id": run_id, "filters": kwargs},
	)

	status = _invoke(tmp_path, "status", "run-1")
	assert status.exit_code == 0, status.output
	assert json.loads(status.output)["data"]["status"] == "completed"

	stopped = _invoke(tmp_path, "stop", "run-1")
	assert stopped.exit_code == 0, stopped.output
	assert json.loads(stopped.output)["data"]["status"] == "stop_requested"

	results = _invoke(tmp_path, "results", "run-1", "--page", "2", "--detail-status", "pending")
	assert results.exit_code == 0, results.output
	assert json.loads(results.output)["data"]["filters"] == {"page": 2, "detail_status": "pending"}

	def missing_status(cache, run_id):
		raise KeyError(run_id)

	def missing_results(cache, run_id, **kwargs):
		raise KeyError(run_id)

	monkeypatch.setattr(crawl, "crawl_status", missing_status)
	monkeypatch.setattr(crawl, "crawl_results", missing_results)
	assert json.loads(_invoke(tmp_path, "status", "missing").output)["error"]["code"] == "JOB_NOT_FOUND"
	assert json.loads(_invoke(tmp_path, "results", "missing").output)["error"]["code"] == "JOB_NOT_FOUND"

	monkeypatch.setattr(crawl, "CacheStore", _fake_cache_factory({"status": "completed"}, stop_result=False))
	assert json.loads(_invoke(tmp_path, "stop", "missing").output)["error"]["code"] == "JOB_NOT_FOUND"


def test_shortlist_command_validates_selection_and_maps_operation_errors(tmp_path, monkeypatch):
	monkeypatch.setattr(crawl, "CacheStore", _fake_cache_factory({"status": "completed"}))
	neither = _invoke(tmp_path, "shortlist", "run-1")
	assert neither.exit_code == 1
	assert json.loads(neither.output)["error"]["code"] == "INVALID_PARAM"

	both = _invoke(tmp_path, "shortlist", "run-1", "--all", "--selector", "csel_1")
	assert both.exit_code == 1
	assert json.loads(both.output)["error"]["code"] == "INVALID_PARAM"

	seen: dict[str, Any] = {}

	def import_ok(cache, run_id, **kwargs):
		seen.update({"run_id": run_id, **kwargs})
		return {"imported": 1}

	monkeypatch.setattr(crawl, "import_crawl_shortlist", import_ok)
	ok = _invoke(
		tmp_path,
		"shortlist",
		"run-1",
		"--selector",
		"csel_1",
		"--tags",
		"AI, 杭州",
		"--note",
		"keep",
	)
	assert ok.exit_code == 0, ok.output
	assert seen == {
		"run_id": "run-1",
		"selectors": ("csel_1",),
		"include_all": False,
		"tags": ("AI", "杭州"),
		"note": "keep",
	}

	def import_missing(cache, run_id, **kwargs):
		raise KeyError(run_id)

	monkeypatch.setattr(crawl, "import_crawl_shortlist", import_missing)
	missing = _invoke(tmp_path, "shortlist", "missing", "--all")
	assert missing.exit_code == 1
	assert json.loads(missing.output)["error"]["code"] == "JOB_NOT_FOUND"

	def import_invalid(cache, run_id, **kwargs):
		raise ValueError("selector invalid")

	monkeypatch.setattr(crawl, "import_crawl_shortlist", import_invalid)
	invalid = _invoke(tmp_path, "shortlist", "run-1", "--all")
	assert invalid.exit_code == 1
	assert json.loads(invalid.output)["error"]["code"] == "INVALID_PARAM"
