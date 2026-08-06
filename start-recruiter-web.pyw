"""Double-click launcher for the local recruiter Web console."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "src"
if SOURCE.is_dir():
	sys.path.insert(0, str(SOURCE))

from boss_agent_cli.web.server import main  # noqa: E402

main([])
