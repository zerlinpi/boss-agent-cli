import http.client
import threading

from boss_agent_cli.web import RecruiterWebController, build_server


def _serve_once(server) -> None:
	server.handle_request()


def test_recruiter_web_rejects_non_loopback_host_header(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	server, application = build_server(controller, port=0)
	thread = threading.Thread(target=_serve_once, args=(server,))
	thread.start()
	try:
		connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
		connection.request("GET", "/", headers={"Host": "evil.example"})
		response = connection.getresponse()
		body = response.read().decode("utf-8")
		connection.close()
		assert response.status == 421
		assert "INVALID_HOST" in body
	finally:
		thread.join(timeout=3)
		application.tasks.close()
		server.server_close()


def test_recruiter_web_accepts_loopback_host_header(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	server, application = build_server(controller, port=0)
	thread = threading.Thread(target=_serve_once, args=(server,))
	thread.start()
	try:
		connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
		connection.request("GET", "/", headers={"Host": f"127.0.0.1:{server.server_port}"})
		response = connection.getresponse()
		body = response.read().decode("utf-8")
		connection.close()
		assert response.status == 200
		assert "BOSS Recruit AI" in body
	finally:
		thread.join(timeout=3)
		application.tasks.close()
		server.server_close()
