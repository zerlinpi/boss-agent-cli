"""Loopback-only HTTP server for the recruiter Web console."""

from __future__ import annotations

import argparse
import json
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Timer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from boss_agent_cli.web.controller import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.tasks import TaskManager

MAX_JSON_BODY = 64 * 1024 * 1024
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
_ASSET_TYPES = {
	"index.html": "text/html; charset=utf-8",
	"app.js": "text/javascript; charset=utf-8",
	"styles.css": "text/css; charset=utf-8",
}
_ASYNC_PATHS = {
	"/api/auth/login",
	"/api/screen/local",
	"/api/screen/boss",
	"/api/jobs/analyze",
}


class RecruiterWebApplication:
	"""Route Web API calls to a controller and persistent background task registry."""

	def __init__(self, controller: RecruiterWebController, *, token: str | None = None):
		self.controller = controller
		self.token = token or secrets.token_urlsafe(24)
		self.tasks = TaskManager(storage_path=controller.data_dir / "recruiter-ai" / "web_tasks.db")

	def asset(self, name: str) -> tuple[bytes, str]:
		asset = files("boss_agent_cli.web.assets").joinpath(name)
		if not asset.is_file():
			raise FileNotFoundError(name)
		content = asset.read_bytes()
		if name == "styles.css":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("layout.css").read_bytes()
		if name in {"index.html", "app.js"}:
			content = content.replace(b"__BOSS_WEB_TOKEN__", self.token.encode("utf-8"))
		return content, _ASSET_TYPES.get(name, "application/octet-stream")

	def authorized(self, handler: BaseHTTPRequestHandler) -> bool:
		return secrets.compare_digest(handler.headers.get("X-Boss-Web-Token", ""), self.token)

	def get(self, path: str, query: dict[str, list[str]]) -> Any:
		if path == "/api/bootstrap":
			return {**self.controller.bootstrap(), "tasks": self.tasks.list(limit=20)}
		if path == "/api/jobs":
			return {"items": self.controller.list_jobs()}
		if path.startswith("/api/jobs/"):
			return self.controller.get_job(unquote(path.removeprefix("/api/jobs/")))
		if path == "/api/candidates":
			return self.controller.candidates(
				_query_one(query, "job_key"), top=_query_int(query, "top", 200),
			)
		if path == "/api/analytics":
			return self.controller.analytics(_query_one(query, "job_key"))
		if path == "/api/export/candidates":
			return self.controller.export_candidates(_query_one(query, "job_key"))
		if path.startswith("/api/candidates/"):
			return self.controller.candidate_detail(unquote(path.removeprefix("/api/candidates/")))
		if path == "/api/report":
			return self.controller.report(
				_query_one(query, "job_key"), top=_query_int(query, "top", 10),
			)
		if path == "/api/replies":
			return {"items": self.controller.replies(
				evaluation_id=_query_optional(query, "evaluation_id"),
				limit=_query_int(query, "limit", 100),
			)}
		if path == "/api/audit":
			return {"items": self.controller.audit_events(
				limit=_query_int(query, "limit", 100),
				action=_query_optional(query, "action"),
			)}
		if path == "/api/tasks":
			return {"items": self.tasks.list(limit=_query_int(query, "limit", 50))}
		if path.startswith("/api/tasks/"):
			task_id = unquote(path.removeprefix("/api/tasks/"))
			try:
				return self.tasks.get(task_id)
			except KeyError as exc:
				raise WebConsoleError("TASK_NOT_FOUND", "任务不存在", status=404) from exc
		if path == "/api/auth/status":
			return self.controller.auth_status()
		raise WebConsoleError("NOT_FOUND", "接口不存在", status=404)

	def post(self, path: str, payload: dict[str, Any]) -> Any:
		if path == "/api/jobs":
			return self.controller.save_job(payload)
		if path == "/api/jobs/analyze":
			return self.tasks.submit(
				"analyze-job",
				lambda progress: self.controller.analyze_job(payload, progress=progress),
				metadata={"title": "AI 分析岗位 JD"},
			)
		if path == "/api/settings/ai":
			return self.controller.configure_ai(payload)
		if path == "/api/settings/mode":
			return self.controller.set_operating_mode(str(payload.get("mode") or ""))
		if path == "/api/auth/login":
			return self.tasks.submit(
				"login",
				lambda progress: self.controller.login(
					timeout=int(payload.get("timeout", 180)),
					cookie_source=str(payload.get("cookie_source") or "") or None,
					force_cdp=bool(payload.get("force_cdp", False)),
					progress=progress,
				),
				metadata={"title": "BOSS 登录"},
			)
		if path == "/api/screen/local":
			return self.tasks.submit(
				"screen-local",
				lambda progress: self.controller.screen_local(payload, progress=progress),
				metadata={"title": "本地简历筛选", "job_key": payload.get("job_key")},
			)
		if path == "/api/screen/boss":
			return self.tasks.submit(
				"screen-boss",
				lambda progress: self.controller.screen_boss(payload, progress=progress),
				metadata={"title": "BOSS 候选人筛选", "job_key": payload.get("job_key")},
			)
		if path == "/api/replies":
			return self.controller.generate_reply(payload)
		if path == "/api/candidates/bulk-status":
			return self.controller.bulk_mark_candidates(payload)
		if path.startswith("/api/candidates/") and path.endswith("/status"):
			evaluation_id = unquote(path[len("/api/candidates/"):-len("/status")].strip("/"))
			return self.controller.mark_candidate(
				evaluation_id,
				str(payload.get("status") or ""),
				str(payload.get("note") or ""),
			)
		raise WebConsoleError("NOT_FOUND", "接口不存在", status=404)


class RecruiterRequestHandler(BaseHTTPRequestHandler):
	"""Serve the single-page UI and JSON API."""

	application: RecruiterWebApplication
	server_version = "BossRecruiterWeb/2.0"

	def do_GET(self) -> None:  # noqa: N802
		if not self._require_loopback_host():
			return
		parsed = urlparse(self.path)
		assets = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
		if parsed.path in assets:
			self._send_asset(assets[parsed.path])
			return
		if parsed.path == "/favicon.ico":
			self.send_response(HTTPStatus.NO_CONTENT)
			self.end_headers()
			return
		if not parsed.path.startswith("/api/"):
			self._send_error(WebConsoleError("NOT_FOUND", "页面不存在", status=404))
			return
		if not self._require_authorized():
			return
		try:
			self._send_json(self.application.get(parsed.path, parse_qs(parsed.query)))
		except WebConsoleError as exc:
			self._send_error(exc)
		except Exception as exc:
			self._send_error(WebConsoleError("INTERNAL_ERROR", str(exc), status=500))

	def do_POST(self) -> None:  # noqa: N802
		if not self._require_loopback_host():
			return
		parsed = urlparse(self.path)
		if not parsed.path.startswith("/api/"):
			self._send_error(WebConsoleError("NOT_FOUND", "接口不存在", status=404))
			return
		if not self._require_authorized():
			return
		try:
			result = self.application.post(parsed.path, self._read_json())
			status = HTTPStatus.ACCEPTED if parsed.path in _ASYNC_PATHS else HTTPStatus.OK
			self._send_json(result, status=status)
		except WebConsoleError as exc:
			self._send_error(exc)
		except (TypeError, ValueError, json.JSONDecodeError) as exc:
			self._send_error(WebConsoleError("INVALID_JSON", str(exc), status=400))
		except Exception as exc:
			self._send_error(WebConsoleError("INTERNAL_ERROR", str(exc), status=500))

	def _require_loopback_host(self) -> bool:
		raw_host = self.headers.get("Host", "").strip()
		try:
			host = urlparse(f"//{raw_host}").hostname
		except ValueError:
			host = None
		if host is not None and host.casefold() in _ALLOWED_HOSTS:
			return True
		self._send_error(WebConsoleError("INVALID_HOST", "本地控制台拒绝非回环 Host 请求", status=421))
		return False

	def _require_authorized(self) -> bool:
		if self.application.authorized(self):
			return True
		self._send_error(WebConsoleError("UNAUTHORIZED", "本地控制台令牌无效", status=401))
		return False

	def _read_json(self) -> dict[str, Any]:
		try:
			length = int(self.headers.get("Content-Length", "0"))
		except ValueError as exc:
			raise WebConsoleError("INVALID_LENGTH", "Content-Length 无效", status=400) from exc
		if length <= 0:
			return {}
		if length > MAX_JSON_BODY:
			raise WebConsoleError("PAYLOAD_TOO_LARGE", "请求内容超过 64 MB", status=413)
		payload = json.loads(self.rfile.read(length).decode("utf-8"))
		if not isinstance(payload, dict):
			raise WebConsoleError("INVALID_JSON", "JSON 顶层必须是对象")
		return payload

	def _security_headers(self) -> None:
		self.send_header("Cache-Control", "no-store")
		self.send_header("X-Content-Type-Options", "nosniff")
		self.send_header("X-Frame-Options", "DENY")
		self.send_header("Referrer-Policy", "no-referrer")
		self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

	def _send_asset(self, name: str) -> None:
		try:
			content, content_type = self.application.asset(name)
		except FileNotFoundError:
			self._send_error(WebConsoleError("NOT_FOUND", "静态资源不存在", status=404))
			return
		self.send_response(HTTPStatus.OK)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(content)))
		self._security_headers()
		self.send_header(
			"Content-Security-Policy",
			"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
		)
		self.end_headers()
		self.wfile.write(content)

	def _send_json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
		body = json.dumps({"ok": True, "data": payload}, ensure_ascii=False).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(body)))
		self._security_headers()
		self.end_headers()
		self.wfile.write(body)

	def _send_error(self, error: WebConsoleError) -> None:
		body = json.dumps({
			"ok": False,
			"error": {"code": error.code, "message": str(error)},
		}, ensure_ascii=False).encode("utf-8")
		self.send_response(error.status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(body)))
		self._security_headers()
		self.end_headers()
		self.wfile.write(body)

	def log_message(self, format: str, *args: Any) -> None:
		return


def _query_one(query: dict[str, list[str]], name: str) -> str:
	value = _query_optional(query, name)
	if not value:
		raise WebConsoleError("INVALID_PARAM", f"缺少查询参数: {name}")
	return value


def _query_optional(query: dict[str, list[str]], name: str) -> str | None:
	values = query.get(name)
	return values[0] if values else None


def _query_int(query: dict[str, list[str]], name: str, default: int) -> int:
	value = _query_optional(query, name)
	try:
		return int(value) if value is not None else default
	except ValueError as exc:
		raise WebConsoleError("INVALID_PARAM", f"{name} 必须是整数") from exc


def build_server(
	controller: RecruiterWebController,
	*,
	host: str = "127.0.0.1",
	port: int = 8765,
) -> tuple[ThreadingHTTPServer, RecruiterWebApplication]:
	if host not in {"127.0.0.1", "localhost"}:
		raise ValueError("Web 控制台只允许绑定本机回环地址")
	application = RecruiterWebApplication(controller)

	class Handler(RecruiterRequestHandler):
		pass

	Handler.application = application
	return ThreadingHTTPServer((host, port), Handler), application


def main(argv: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(description="BOSS 招聘 AI 本地 Web 控制台")
	parser.add_argument("--data-dir", default="~/.boss-agent")
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=8765)
	parser.add_argument("--platform", default="zhipin")
	parser.add_argument("--cdp-url", default=None)
	parser.add_argument("--no-open", action="store_true")
	args = parser.parse_args(argv)
	controller = RecruiterWebController(
		Path(args.data_dir), platform=args.platform, cdp_url=args.cdp_url,
	)
	server, application = build_server(controller, host=args.host, port=args.port)
	url = f"http://{args.host}:{server.server_port}/"
	if not args.no_open:
		Timer(0.4, lambda: webbrowser.open(url)).start()
	print(f"BOSS 招聘 AI 控制台已启动: {url}")
	print("该服务仅监听本机；关闭此窗口即可停止。")
	try:
		server.serve_forever(poll_interval=0.5)
	except KeyboardInterrupt:
		pass
	finally:
		application.tasks.close()
		server.server_close()


if __name__ == "__main__":
	main()
