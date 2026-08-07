"""Container entry point for the recruiter Web workspace.

The public host port should be published on the host loopback interface only.
Inside the container we bind to 0.0.0.0 so Docker's port forwarding can reach it.
"""

from __future__ import annotations

import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from boss_agent_cli.web.controller import RecruiterWebController
from boss_agent_cli.web.server import RecruiterRequestHandler, RecruiterWebApplication


def _port() -> int:
    raw = os.environ.get("BOSS_WEB_PORT", "8765")
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit("BOSS_WEB_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("BOSS_WEB_PORT must be between 1 and 65535")
    return port


def main() -> None:
    data_dir = Path(os.environ.get("BOSS_DATA_DIR", "/data/.boss-agent"))
    cdp_url = os.environ.get("BOSS_CDP_URL") or None
    controller = RecruiterWebController(data_dir, platform="zhipin", cdp_url=cdp_url)
    application = RecruiterWebApplication(controller)

    class Handler(RecruiterRequestHandler):
        pass

    Handler.application = application
    port = _port()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"BOSS Recruit AI container is ready on port {port}")
    print("Publish this port to 127.0.0.1 on the Docker host.")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        application.tasks.close()
        server.server_close()


if __name__ == "__main__":
    main()
