import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from boss_agent_cli.automation import zhilian_cdp


def test_find_zhilian_page_prefers_chat_and_rejects_lookalike_hosts():
	lookalike = SimpleNamespace(url="https://zhaopin.com.evil.example/app/im")
	generic = SimpleNamespace(url="https://rd6.zhaopin.com/home")
	im_page = SimpleNamespace(url="https://rd6.zhaopin.com/im/inbox")
	chat_page = SimpleNamespace(url="https://rd6.zhaopin.com/app/im")
	assert zhilian_cdp._find_zhilian_page([lookalike, generic, im_page, chat_page]) is im_page
	assert zhilian_cdp._find_zhilian_page([lookalike, generic]) is generic
	assert zhilian_cdp._find_zhilian_page([lookalike]) is None


def test_zhilian_chat_url_detection_is_path_based():
	assert zhilian_cdp._is_zhilian_chat_url("https://rd6.zhaopin.com/app/im") is True
	assert zhilian_cdp._is_zhilian_chat_url("https://rd6.zhaopin.com/chat/123") is True
	assert zhilian_cdp._is_zhilian_chat_url("https://rd6.zhaopin.com/home") is False


def _install_fake_patchright(monkeypatch, playwright) -> None:
	module = types.ModuleType("patchright.sync_api")
	module.sync_playwright = lambda: SimpleNamespace(start=lambda: playwright)
	monkeypatch.setitem(sys.modules, "patchright.sync_api", module)


def test_create_session_reuses_existing_zhilian_page(tmp_path, monkeypatch):
	page = SimpleNamespace(url="https://rd6.zhaopin.com/app/im")
	context = SimpleNamespace(pages=[page])
	connect_calls: list[str] = []
	playwright = SimpleNamespace(
		chromium=SimpleNamespace(
			connect_over_cdp=lambda endpoint: (
				connect_calls.append(endpoint),
				SimpleNamespace(contexts=[context]),
			)[1]
		),
		stop=lambda: None,
	)
	_install_fake_patchright(monkeypatch, playwright)
	monkeypatch.setattr(zhilian_cdp, "probe_cdp", lambda endpoint: "ws://fixture-cdp")
	captured: dict[str, object] = {}

	class Session:
		def __init__(self, selected_page, *, diagnostics_dir: Path | None):
			captured["page"] = selected_page
			captured["diagnostics_dir"] = diagnostics_dir

	monkeypatch.setattr(zhilian_cdp, "ZhilianBrowserRecruiterSession", Session)
	result = zhilian_cdp.create_zhilian_browser_session_from_cdp(
		cdp_url="http://127.0.0.1:9222",
		diagnostics_dir=tmp_path,
	)
	assert isinstance(result, Session)
	assert connect_calls == ["ws://fixture-cdp"]
	assert captured == {"page": page, "diagnostics_dir": tmp_path}


def test_create_session_opens_official_chat_when_context_has_no_zhilian_page(tmp_path, monkeypatch):
	goto_calls: list[tuple[str, str, int]] = []

	class NewPage:
		url = "about:blank"

		def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
			goto_calls.append((url, wait_until, timeout))

	new_page = NewPage()
	context = SimpleNamespace(
		pages=[SimpleNamespace(url="https://example.com")],
		new_page=lambda: new_page,
	)
	playwright = SimpleNamespace(
		chromium=SimpleNamespace(connect_over_cdp=lambda endpoint: SimpleNamespace(contexts=[context])),
		stop=lambda: None,
	)
	_install_fake_patchright(monkeypatch, playwright)
	monkeypatch.setattr(zhilian_cdp, "probe_cdp", lambda endpoint: None)
	monkeypatch.setattr(
		zhilian_cdp,
		"ZhilianBrowserRecruiterSession",
		lambda page, diagnostics_dir=None: SimpleNamespace(page=page, diagnostics_dir=diagnostics_dir),
	)
	result = zhilian_cdp.create_zhilian_browser_session_from_cdp(
		cdp_url="http://127.0.0.1:9333",
		diagnostics_dir=tmp_path,
	)
	assert result.page is new_page
	assert goto_calls == [
		(zhilian_cdp.ZhilianRecruiterSelectors().chat_urls[0], "domcontentloaded", 15000)
	]


def test_create_session_stops_playwright_on_connect_failure(monkeypatch):
	stopped: list[bool] = []

	def fail_connect(endpoint: str):
		raise RuntimeError("fixture connection failure")

	playwright = SimpleNamespace(
		chromium=SimpleNamespace(connect_over_cdp=fail_connect),
		stop=lambda: stopped.append(True),
	)
	_install_fake_patchright(monkeypatch, playwright)
	monkeypatch.setattr(zhilian_cdp, "probe_cdp", lambda endpoint: None)
	with pytest.raises(RuntimeError, match="cannot connect to CDP Chrome"):
		zhilian_cdp.create_zhilian_browser_session_from_cdp(
			cdp_url="http://127.0.0.1:9444",
			diagnostics_dir=None,
		)
	assert stopped == [True]


def test_create_session_rejects_browser_without_context(monkeypatch):
	stopped: list[bool] = []
	playwright = SimpleNamespace(
		chromium=SimpleNamespace(connect_over_cdp=lambda endpoint: SimpleNamespace(contexts=[])),
		stop=lambda: stopped.append(True),
	)
	_install_fake_patchright(monkeypatch, playwright)
	monkeypatch.setattr(zhilian_cdp, "probe_cdp", lambda endpoint: "ws://fixture")
	with pytest.raises(RuntimeError, match="no browser context"):
		zhilian_cdp.create_zhilian_browser_session_from_cdp(cdp_url=None, diagnostics_dir=None)
	assert stopped == [True]
