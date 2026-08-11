import http.client
import threading

from boss_agent_cli.web import RecruiterWebController, build_server


def _request_once(tmp_path, method: str, *, host: str, origin: str | None = None):
	controller = RecruiterWebController(tmp_path)
	server, application = build_server(controller, port=0)
	thread = threading.Thread(target=server.handle_request)
	thread.start()
	try:
		headers = {"Host": host}
		if origin is not None:
			headers["Origin"] = origin
		connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
		connection.request(method, "/api/bootstrap", headers=headers)
		response = connection.getresponse()
		body = response.read().decode("utf-8")
		connection.close()
		return response.status, body
	finally:
		thread.join(timeout=3)
		application.tasks.close()
		server.server_close()


def test_unknown_http_verb_rejects_non_loopback_host_before_dispatch(tmp_path) -> None:
	status, body = _request_once(tmp_path, "OPTIONS", host="evil.example")
	assert status == 421
	assert "INVALID_HOST" in body


def test_unknown_http_verb_rejects_remote_origin_before_dispatch(tmp_path) -> None:
	status, body = _request_once(
		tmp_path,
		"OPTIONS",
		host="127.0.0.1",
		origin="https://evil.example",
	)
	assert status == 403
	assert "INVALID_LOCAL_ORIGIN" in body


def test_unknown_http_verb_with_local_boundary_reaches_normal_501(tmp_path) -> None:
	status, _ = _request_once(
		tmp_path,
		"OPTIONS",
		host="127.0.0.1",
		origin="http://127.0.0.1",
	)
	assert status == 501
