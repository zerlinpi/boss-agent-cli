from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from boss_agent_cli.crawler import transport
from boss_agent_cli.crawler.transport import CrawlRiskError, DrissionCrawlerSession


def _session(tmp_path: Path) -> DrissionCrawlerSession:
	return DrissionCrawlerSession(
		profile_path=tmp_path / "profile",
		chrome_path=None,
		cdp_port=9444,
		hook_profile="none",
		hook_dir=None,
	)


def test_detail_client_copies_browser_cookies_and_stoken_without_exposing_values(tmp_path, monkeypatch):
	created: dict[str, Any] = {}

	class Response:
		def raise_for_status(self) -> None:
			created["raised"] = True

		def json(self):
			return {"code": 0, "zpData": {"jobCard": {"postDescription": "公开职位描述"}}}

	class Client:
		def __init__(self, **kwargs: Any) -> None:
			created["client_kwargs"] = kwargs

		def get(self, url: str, *, params: dict[str, str]):
			created["url"] = url
			created["params"] = params
			return Response()

		def close(self) -> None:
			created["closed"] = True

	monkeypatch.setattr(transport.httpx, "Client", Client)
	session = _session(tmp_path)
	session._page = SimpleNamespace(
		user_agent="test-agent",
		cookies=lambda: [
			{"name": "session_cookie", "value": "fixture-secret"},
			{"name": "__zp_stoken__", "value": "fixture-stoken"},
		],
	)

	payload = session.fetch_detail("fixture-security-id")
	assert payload["code"] == 0
	assert created["url"] == transport.JOB_CARD_URL
	assert created["params"] == {
		"securityId": "fixture-security-id",
		"__zp_stoken__": "fixture-stoken",
	}
	assert created["client_kwargs"]["cookies"] == {
		"session_cookie": "fixture-secret",
		"__zp_stoken__": "fixture-stoken",
	}
	assert created["client_kwargs"]["headers"]["User-Agent"] == "test-agent"
	assert created["raised"] is True


def test_fetch_detail_empty_identifier_is_local_and_non_object_response_is_rejected(tmp_path, monkeypatch):
	session = _session(tmp_path)
	assert session.fetch_detail("") == {"code": 0, "zpData": {"jobCard": {}}}

	class Client:
		def get(self, url: str, *, params: dict[str, str]):
			return SimpleNamespace(raise_for_status=lambda: None, json=lambda: ["unexpected"])

	session._details = Client()
	with pytest.raises(RuntimeError, match="job_card 响应不是对象"):
		session.fetch_detail("fixture-security-id")


def test_security_page_and_risk_codes_stop_crawl_immediately(tmp_path):
	session = _session(tmp_path)
	session._page = SimpleNamespace(url="https://www.zhipin.com/zhipin-security", html="")
	with pytest.raises(CrawlRiskError, match="zhipin-security"):
		session._raise_if_security_page()

	session._page = SimpleNamespace(url="https://www.zhipin.com/web/geek/jobs", html="security zhipin-security challenge")
	with pytest.raises(CrawlRiskError, match="zhipin-security"):
		session._raise_if_security_page()

	for code in (37, 38):
		with pytest.raises(CrawlRiskError, match=f"code={code}"):
			session._raise_if_risk_response({"code": code, "message": "fixture risk"})


def test_missing_job_list_container_is_treated_as_risk_but_probe_errors_are_not(tmp_path):
	session = _session(tmp_path)

	class MissingPage:
		url = "https://www.zhipin.com/web/geek/jobs"
		html = "normal"

		def ele(self, selector: str, timeout: int = 0):
			return None

	session._page = MissingPage()
	with pytest.raises(CrawlRiskError, match="缺少职位列表容器"):
		session._raise_if_security_page(require_job_list=True)

	class ProbeFailurePage:
		url = "https://www.zhipin.com/web/geek/jobs"
		html = "normal"

		def ele(self, selector: str, timeout: int = 0):
			raise RuntimeError("DOM probe unavailable")

	session._page = ProbeFailurePage()
	session._raise_if_security_page(require_job_list=True)


def test_close_releases_detail_client_and_browser_page(tmp_path):
	events: list[str] = []

	class Details:
		def close(self) -> None:
			events.append("details")

	class Page:
		def quit(self) -> None:
			events.append("browser")

	session = _session(tmp_path)
	session._details = Details()
	session._page = Page()
	session.close()
	assert events == ["details", "browser"]
	assert session._details is None
	assert session._page is None
