#!/usr/bin/env python3
"""CLI entrypoint for local Web UI."""

import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_web.runtime import resolve_data_dir


def main():
    parser = argparse.ArgumentParser(description="Run local web UI.")
    parser.add_argument(
        "--data-dir", dest="data_dir", help="Path for app data (default ./data)."
    )
    parser.add_argument("--host", dest="host", default="127.0.0.1")
    parser.add_argument("--port", dest="port", type=int, default=8000)
    parser.add_argument("--reload", dest="reload", action="store_true")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "app.db"

    uvicorn.run(
        "game_web.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        kwargs={"db_path": str(db_path), "data_dir": str(data_dir)},
    )


if __name__ == "__main__":
    main()
