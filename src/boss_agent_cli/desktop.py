"""Desktop shell for the local recruiter Web workspace.

The desktop build keeps the existing loopback-only Web application and renders it
inside a native WebView window. BOSS login may still open a dedicated browser
window because the platform login flow is intentionally isolated from the shell.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any

from boss_agent_cli.web import RecruiterWebController, build_server


def _show_fatal_error(message: str) -> None:
	"""Show startup failures even when the PyInstaller build has no console."""
	if sys.platform == "win32":
		try:
			windll: Any = getattr(ctypes, "windll", None)
			if windll is not None:
				windll.user32.MessageBoxW(0, message, "Boss Recruit AI", 0x10)
				return
		except Exception:
			pass
	print(message, file=sys.stderr)


def _require_desktop_dependencies() -> Any:
	try:
		import webview
		from pypdf import PdfReader
	except ImportError as exc:
		raise RuntimeError(
			"桌面运行依赖缺失。请使用 build-recruiter-exe.bat 构建桌面版，"
			"或安装 pywebview/pypdf 后再运行。"
		) from exc
	if not callable(getattr(webview, "create_window", None)) or not callable(PdfReader):
		raise RuntimeError("桌面运行依赖加载不完整")
	return webview


def run_self_test() -> None:
	"""Validate imports, packaged Web assets, and loopback server construction."""
	_require_desktop_dependencies()
	with TemporaryDirectory(prefix="boss-recruit-ai-self-test-") as temporary:
		controller = RecruiterWebController(Path(temporary), platform="zhipin")
		server, application = build_server(controller, host="127.0.0.1", port=0)
		try:
			if server.server_port <= 0:
				raise RuntimeError("桌面自检失败：本地服务未分配端口")
			checks = {
				"index.html": b"BOSS Recruit AI",
				"app.js": b"RECRUITER AUTOPILOT",
				"styles.css": b"--primary",
			}
			for name, marker in checks.items():
				content, _content_type = application.asset(name)
				if marker not in content:
					raise RuntimeError(f"桌面自检失败：{name} 资源不完整")
		finally:
			application.tasks.close()
			server.server_close()


def run_desktop(
	*,
	data_dir: Path,
	platform: str = "zhipin",
	cdp_url: str | None = None,
	width: int = 1440,
	height: int = 900,
) -> None:
	"""Run the recruiter workspace in a native desktop window."""
	webview = _require_desktop_dependencies()
	controller = RecruiterWebController(data_dir.expanduser(), platform=platform, cdp_url=cdp_url)
	server, application = build_server(controller, host="127.0.0.1", port=0)
	url = f"http://127.0.0.1:{server.server_port}/"
	thread = Thread(
		target=server.serve_forever,
		kwargs={"poll_interval": 0.25},
		name="boss-recruit-web",
		daemon=True,
	)
	thread.start()

	try:
		webview.create_window(
			"Boss Recruit AI",
			url=url,
			width=max(1080, int(width)),
			height=max(720, int(height)),
			min_size=(980, 680),
			text_select=True,
		)
		webview.start(debug=False)
	finally:
		server.shutdown()
		application.tasks.close()
		server.server_close()
		thread.join(timeout=3)


def main(argv: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(description="Boss Recruit AI Windows desktop shell")
	parser.add_argument("--data-dir", default="~/.boss-agent")
	parser.add_argument("--platform", default="zhipin")
	parser.add_argument("--cdp-url", default=None)
	parser.add_argument("--width", type=int, default=1440)
	parser.add_argument("--height", type=int, default=900)
	parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
	args = parser.parse_args(argv)
	if args.self_test:
		try:
			run_self_test()
		except Exception as exc:
			print(f"Boss Recruit AI self-test failed: {exc}", file=sys.stderr)
			raise SystemExit(1) from exc
		return
	try:
		run_desktop(
			data_dir=Path(args.data_dir),
			platform=args.platform,
			cdp_url=args.cdp_url,
			width=args.width,
			height=args.height,
		)
	except Exception as exc:
		_show_fatal_error(f"Boss Recruit AI 启动失败：\n\n{exc}")
		raise SystemExit(1) from exc


if __name__ == "__main__":
	main()
