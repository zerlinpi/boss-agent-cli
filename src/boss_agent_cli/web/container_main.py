"""Container entry point for the recruiter Web workspace.

The public host port should be published on the host loopback interface only.
Inside the container we bind to 0.0.0.0 so Docker's port forwarding can reach it.
"""

from __future__ import annotations

import os
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from boss_agent_cli.auth.token_store import TokenStore
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


def _write_private(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    fd: int | None = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if fd is not None:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def _ensure_persistent_machine_id(data_dir: Path) -> str:
    """Keep encrypted login/API credentials decryptable after container recreation."""
    explicit = os.environ.get("BOSS_AGENT_MACHINE_ID", "").strip()
    if explicit:
        return explicit

    auth_dir = data_dir / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    identity_path = auth_dir / "container-machine-id"
    if identity_path.exists():
        try:
            identity = identity_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit("Unable to read persisted container machine identity") from exc
        if not identity or len(identity) > 1024:
            raise SystemExit("Persisted container machine identity is invalid")
    else:
        # Capture the identity used by legacy TokenStore before setting the environment override.
        # Existing encrypted sessions therefore remain readable on the first upgraded container,
        # while subsequent container recreations reuse this value from the persistent data volume.
        identity = TokenStore(auth_dir)._get_machine_id()
        if not identity:
            raise SystemExit("Unable to determine a stable container machine identity")
        _write_private(identity_path, identity)

    os.environ["BOSS_AGENT_MACHINE_ID"] = identity
    return identity


def main() -> None:
    data_dir = Path(os.environ.get("BOSS_DATA_DIR", "/data/.boss-agent"))
    _ensure_persistent_machine_id(data_dir)
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
