import sys
import time
from typing import Any, cast
from urllib.parse import urlparse

from patchright.sync_api import sync_playwright

LOGIN_PAGE_URL = "https://www.zhipin.com/web/user/"
HOME_URL = "https://www.zhipin.com/"
_DEFAULT_CDP_URL = "http://localhost:9222"

# 超时常量（秒/毫秒）
_CDP_PROBE_TIMEOUT = 3           # CDP 探测 HTTP 超时（秒）
_NAV_TIMEOUT_MS = 15000          # 页面导航超时（毫秒）
_RUNTIME_SETTLE_MS = 3000        # 首页 DOM 到位后给 cookie/stoken 运行时传播的固定等待
_POST_LOGIN_WAIT = 3             # 登录成功后等待 cookie 传播（秒）
_STOKEN_GENERATION_WAIT = 2      # stoken 生成等待（秒）

_PLATFORM_BROWSER_CONFIG: dict[str, dict[str, str]] = {
	"zhipin": {
		"login_page_url": LOGIN_PAGE_URL,
		"home_url": HOME_URL,
		"cookie_domain": "zhipin",
		"success_cookie": "wt2",
	},
	"zhilian": {
		"login_page_url": "https://rd6.zhaopin.com/app/im",
		"home_url": "https://rd6.zhaopin.com/app/im",
		"cookie_domain": "zhaopin",
		"success_cookie": "at",
	},
}
_ZHILIAN_HOST = "zhaopin.com"


def _get_platform_config(platform: str) -> dict[str, str]:
	config = _PLATFORM_BROWSER_CONFIG.get(platform)
	if config is None:
		raise ValueError(f"unsupported platform: {platform}")
	return config


def _launch_chromium(playwright: Any, *, headless: bool) -> Any:
	"""Prefer an installed Chrome/Edge before Patchright's downloaded Chromium.

	Desktop releases intentionally do not bundle a browser runtime. Most Windows
	machines already have Chrome or Edge, so using their supported Playwright
	channels keeps the EXE package much smaller while preserving the existing
	Patchright Chromium fallback for source installs.
	"""
	for channel in ("chrome", "msedge"):
		try:
			return playwright.chromium.launch(channel=channel, headless=headless)
		except Exception:
			continue
	try:
		return playwright.chromium.launch(headless=headless)
	except Exception as exc:
		raise RuntimeError(
			"未找到可用的 Chrome/Edge/Chromium。请先安装 Chrome 或 Edge，"
			"然后重新执行 BOSS 登录。"
		) from exc


def _extract_zhilian_client_id(page: Any) -> str:
	try:
		return cast("str", page.evaluate("""
			() => {
				const keys = ["x-zp-client-id", "x_zp_client_id", "clientId"];
				for (const key of keys) {
					const value = window.localStorage.getItem(key) || window.sessionStorage.getItem(key);
					if (value) return value;
				}
				return '';
			}
		"""))
	except Exception:
		return ""


def _is_zhilian_url(url: str) -> bool:
	host = urlparse(url).hostname
	if host is None:
		return False
	host = host.rstrip(".").lower()
	return host == _ZHILIAN_HOST or host.endswith(f".{_ZHILIAN_HOST}")


def _find_zhilian_recruiter_page(pages: list[Any]) -> Any | None:
	for page in pages:
		url = getattr(page, "url", "")
		if _is_zhilian_url(url) and any(path in url for path in ("/app/im", "/app/recommend")):
			return page
	for page in pages:
		if _is_zhilian_url(getattr(page, "url", "")):
			return page
	return None


def _zhilian_client_id_from(cookies: dict[str, str], page: Any) -> str:
	return cookies.get("x-zp-client-id") or _extract_zhilian_client_id(page)


def _warm_home_for_runtime(page: Any, home_url: str, *, stage: str) -> None:
	"""Load the platform home page and allow browser-side credential state to settle.

	Modern recruiting pages often keep analytics/WebSocket requests open indefinitely,
	so Playwright's ``networkidle`` is not a meaningful readiness signal here. The
	credential extraction path only needs the DOM plus a short propagation window.
	"""
	try:
		page.goto(home_url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
	except Exception:
		print(f"[boss] {stage}：首页仍在加载，继续同步登录凭证", file=sys.stderr)
	else:
		print(f"[boss] {stage}：首页已加载，正在同步登录凭证", file=sys.stderr)
	try:
		page.wait_for_timeout(_RUNTIME_SETTLE_MS)
	except Exception:
		# A closing/replaced page should not turn this best-effort propagation delay
		# into a misleading login failure; extraction below remains authoritative.
		pass


def probe_cdp(cdp_url: str | None = None) -> str | None:
	"""探测 CDP 是否可用，返回 WebSocket URL 或 None。"""
	import httpx
	base = cdp_url or _DEFAULT_CDP_URL
	try:
		resp = httpx.get(f"{base}/json/version", timeout=_CDP_PROBE_TIMEOUT)
		return cast("str | None", resp.json().get("webSocketDebuggerUrl"))
	except (httpx.HTTPError, ValueError, KeyError):
		return None


def login_via_cdp(*, cdp_url: str | None = None, timeout: int = 120, platform: str = "zhipin") -> dict[str, Any]:
	"""
	通过 CDP 连接用户 Chrome 扫码登录。
	返回 token dict，失败抛异常。
	"""
	config = _get_platform_config(platform)
	login_page_url = config["login_page_url"]
	home_url = config["home_url"]
	cookie_domain = config["cookie_domain"]
	success_cookie = config["success_cookie"]
	ws_url = probe_cdp(cdp_url)
	if not ws_url:
		raise ConnectionError("CDP 不可用，请先运行 boss-chrome 启动带调试端口的 Chrome")

	print("[boss] 正在 CDP Chrome 中打开登录页...", file=sys.stderr)
	pw = sync_playwright().start()
	browser = pw.chromium.connect_over_cdp(ws_url)
	ctx = browser.contexts[0] if browser.contexts else browser.new_context()
	page = _find_zhilian_recruiter_page(ctx.pages) if platform == "zhilian" else None
	created_page = page is None
	if page is None:
		page = ctx.new_page()

	try:
		if created_page or platform != "zhilian":
			try:
				page.goto(
					login_page_url,
					wait_until="commit", timeout=_NAV_TIMEOUT_MS,
				)
			except Exception:
				pass

		print(f"[boss] 请在 Chrome 中扫码登录，等待中...（超时 {timeout}s）", file=sys.stderr)

		for i in range(timeout):
			time.sleep(1)
			cookies = ctx.cookies()
			success = [c for c in cookies if c["name"] == success_cookie and cookie_domain in c.get("domain", "")]
			if success:
				print("[boss] 检测到登录成功！", file=sys.stderr)
				break
			if i > 0 and i % 15 == 0:
				print(f"[boss] 等待中... {i}s", file=sys.stderr)
		else:
			raise TimeoutError(f"CDP 扫码登录超时（{timeout}s）")

		if created_page or platform != "zhilian":
			try:
				page.goto(home_url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
			except Exception:
				pass
		all_cookies = {c["name"]: c["value"] for c in ctx.cookies() if cookie_domain in c.get("domain", "")}
		ua = page.evaluate("navigator.userAgent")
		x_zp_client_id = _zhilian_client_id_from(all_cookies, page) if platform == "zhilian" else ""

		result: dict[str, Any] = {"cookies": all_cookies, "stoken": "", "user_agent": ua}
		if x_zp_client_id:
			result["x_zp_client_id"] = x_zp_client_id
		return result
	finally:
		try:
			if created_page:
				page.close()
		finally:
			pw.stop()


def login_via_browser(*, timeout: int = 120, platform: str = "zhipin") -> dict[str, Any]:
	"""
	使用 patchright（Playwright 兼容 fork）打开登录页。
	双重检测登录成功：监听 API 响应 + 轮询 wt2 cookie。
	"""
	config = _get_platform_config(platform)
	login_page_url = config["login_page_url"]
	home_url = config["home_url"]
	cookie_domain = config["cookie_domain"]
	success_cookie = config["success_cookie"]
	with sync_playwright() as p:
		browser = _launch_chromium(p, headless=False)
		context = browser.new_context(
			viewport={"width": 1280, "height": 800},
			locale="zh-CN",
			timezone_id="Asia/Shanghai",
		)
		page = context.new_page()

		page.goto(login_page_url, wait_until="domcontentloaded")
		print("已打开 BOSS 直聘登录页。", file=sys.stderr)
		print(f"请扫码或手机号登录（超时 {timeout} 秒）...", file=sys.stderr)

		# 双重检测：API 响应 或 wt2 cookie 出现，任一触发即认为登录成功
		login_detected = False

		def _on_response(response: Any) -> None:
			nonlocal login_detected
			url = response.url
			if (url.startswith("https://www.zhipin.com/wapi/zppassport/qrcode/loginConfirm")
				or url.startswith("https://www.zhipin.com/wapi/zppassport/qrcode/dispatcher")
				or url.startswith("https://www.zhipin.com/wapi/zppassport/login/phoneV2")):
				login_detected = True

		page.on("response", _on_response)

		deadline = time.time() + timeout
		while time.time() < deadline and not login_detected:
			# 也通过 cookie 检测（覆盖 API 匹配不上的情况）
			try:
				cookies_list = context.cookies()
				if any(c["name"] == success_cookie and cookie_domain in c.get("domain", "") for c in cookies_list):
					login_detected = True
					break
			except Exception:
				pass
			time.sleep(1)

		if not login_detected:
			browser.close()
			raise TimeoutError(f"扫码登录超时（{timeout}秒）")

		print("检测到登录成功，正在提取凭证...", file=sys.stderr)
		time.sleep(_POST_LOGIN_WAIT)

		# 跳转主站提取完整 cookies 和 stoken
		_warm_home_for_runtime(page, home_url, stage="登录后回到首页")

		cookies_list = context.cookies()
		cookies = {c["name"]: c["value"] for c in cookies_list if cookie_domain in c.get("domain", "")}
		user_agent = page.evaluate("navigator.userAgent")
		stoken = _extract_stoken(page) if platform == "zhipin" else ""
		x_zp_client_id = _extract_zhilian_client_id(page) if platform == "zhilian" else ""

		browser.close()

	result: dict[str, Any] = {
		"cookies": cookies,
		"stoken": stoken,
		"user_agent": user_agent,
	}
	if x_zp_client_id:
		result["x_zp_client_id"] = x_zp_client_id
	return result


def refresh_stoken_via_cdp(cdp_url: str | None = None) -> str:
	"""通过 CDP Chrome 刷新 stoken（指纹一致，不会被拒）。"""
	ws_url = probe_cdp(cdp_url)
	if not ws_url:
		raise ConnectionError("CDP 不可用")

	pw = sync_playwright().start()
	browser = pw.chromium.connect_over_cdp(ws_url)
	ctx = browser.contexts[0] if browser.contexts else browser.new_context()
	page = ctx.new_page()

	try:
		page.goto(HOME_URL, wait_until="commit", timeout=15000)
	except Exception:
		pass
	time.sleep(_STOKEN_GENERATION_WAIT)

	stoken = _extract_stoken(page)
	page.close()
	pw.stop()

	if not stoken:
		raise RuntimeError("CDP 刷新 stoken 失败：页面未生成 stoken")
	return stoken


def refresh_stoken(cookies: dict[str, Any], user_agent: str) -> str:
	"""通过 headless patchright 刷新 stoken（兜底方案）。"""
	with sync_playwright() as p:
		browser = _launch_chromium(p, headless=True)
		context = browser.new_context(user_agent=user_agent)
		context.add_cookies([
			{"name": name, "value": value, "domain": ".zhipin.com", "path": "/"}
			for name, value in cookies.items()
		])
		page = context.new_page()
		_warm_home_for_runtime(page, HOME_URL, stage="刷新 stoken")
		stoken = _extract_stoken(page)
		browser.close()

	return stoken


def _extract_stoken(page: Any) -> str:
	try:
		stoken = page.evaluate("""
			() => {
				const match = document.cookie.match(/__zp_stoken__=([^;]+)/);
				return match ? match[1] : '';
			}
		""")
		if not stoken:
			stoken = page.evaluate("() => window.__zp_stoken__ || ''")
		return cast("str", stoken)
	except Exception:
		return ""
