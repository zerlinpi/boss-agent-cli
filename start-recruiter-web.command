#!/bin/zsh
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$ROOT/.venv/bin/python" ]; then
	PYTHON="$ROOT/.venv/bin/python"
else
	PYTHON="$(command -v python3)"
fi
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" exec "$PYTHON" -m boss_agent_cli.web
