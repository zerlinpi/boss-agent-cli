from boss_agent_cli.auth import browser as browser_module


class _FakePage:
	def __init__(self, *, fail_goto: bool = False) -> None:
		self.fail_goto = fail_goto
		self.goto_calls: list[tuple[str, str, int]] = []
		self.wait_calls: list[int] = []

	def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
		self.goto_calls.append((url, wait_until, timeout))
		if self.fail_goto:
			raise RuntimeError("navigation still busy")

	def wait_for_timeout(self, timeout: int) -> None:
		self.wait_calls.append(timeout)


def test_warm_home_uses_dom_ready_plus_fixed_settle_window(capsys) -> None:
	page = _FakePage()

	browser_module._warm_home_for_runtime(page, "https://www.zhipin.com/", stage="登录后回到首页")

	assert page.goto_calls == [(
		"https://www.zhipin.com/",
		"domcontentloaded",
		browser_module._NAV_TIMEOUT_MS,
	)]
	assert page.wait_calls == [browser_module._RUNTIME_SETTLE_MS]
	stderr = capsys.readouterr().err
	assert "首页已加载，正在同步登录凭证" in stderr
	assert "networkidle" not in stderr
	assert "Timeout" not in stderr


def test_warm_home_navigation_delay_is_not_reported_as_login_failure(capsys) -> None:
	page = _FakePage(fail_goto=True)

	browser_module._warm_home_for_runtime(page, "https://www.zhipin.com/", stage="登录后回到首页")

	assert page.wait_calls == [browser_module._RUNTIME_SETTLE_MS]
	stderr = capsys.readouterr().err
	assert "首页仍在加载，继续同步登录凭证" in stderr
	assert "navigation still busy" not in stderr
	assert "networkidle" not in stderr
