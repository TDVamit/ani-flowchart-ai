"""
start.py — development and production launcher for the Audit Dashboard backend.

Usage:
    python start.py            # auto-detects mode from ENV variable
    python start.py --dev      # force development (hot-reload, debug)
    python start.py --prod     # force production (multi-worker, no reload)
    python start.py --port 9000
"""

import argparse
import os
import sys

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Dashboard API server")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dev", action="store_true", help="Development mode (reload on change)")
    mode.add_argument("--prod", action="store_true", help="Production mode (multi-worker)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes (prod only, default: cpu_count)",
    )
    args = parser.parse_args()

    # Resolve mode: explicit flag > ENV > default (dev)
    env = os.getenv("APP_ENV", "development").lower()
    is_prod = args.prod or (not args.dev and env == "production")

    if is_prod:
        worker_count = args.workers or (os.cpu_count() or 1)
        print(f"[start] Production mode — {worker_count} workers on {args.host}:{args.port}")
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            workers=worker_count,
            # Use a process manager (gunicorn / systemd) in real prod;
            # uvicorn multi-worker is fine for single-server deployments.
            loop="uvloop",
            http="httptools",
            access_log=True,
            log_level="info",
        )
    else:
        print(f"[start] Development mode — hot-reload on {args.host}:{args.port}")
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=["."],
            loop="asyncio",   # asyncio loop plays nicer with watchfiles reloader
            log_level="debug",
        )


if __name__ == "__main__":
    main()
