"""Starts the server, and writes down everything that happens to it.

The installed copy runs in a hidden window, so anything it prints is lost the
moment it is printed. That is how a server can fail to start with nobody able
to see why. This launcher sends every line to logs/server.log as well as to
the screen, including the error if the application cannot even load.

It also refuses to start a second copy. Two servers on the same port is not
an error on Windows: one listening on the network and one on this computer
can both succeed, and then some screens talk to one and some to the other.

    python run_server.py --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import argparse
import copy
import logging
import logging.handlers
import os
import socket
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
LOG_FILE = LOGS / "server.log"


def _file_handler() -> logging.Handler:
    LOGS.mkdir(exist_ok=True)
    # Five files of one megabyte each: weeks of normal use, and a full disk
    # is never something a log should cause.
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    return handler


def _port_taken(port: int) -> bool:
    """True when something already answers on this port on this computer."""
    for host in ("127.0.0.1", "::1"):
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                if probe.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    log = logging.getLogger("greenbuffet")
    log.setLevel(logging.INFO)
    file_handler = _file_handler()
    log.addHandler(file_handler)
    log.addHandler(logging.StreamHandler(sys.stdout))
    # The root logger also writes to the file once the server runs; without
    # this, every line of ours would be written twice.
    log.propagate = False

    if _port_taken(args.port):
        log.error(
            "Port %s is already in use, so this copy is not starting. Another copy of "
            "The Green Buffet (or something else) is running. Run scripts\\status.ps1 "
            "to see what it is.", args.port,
        )
        return 2

    log.info("Starting on %s:%s", args.host, args.port)
    try:
        import uvicorn

        from app.core.config import ENV_FILE, settings
        from app.main import app  # an import error here is the classic silent failure
    except Exception:
        log.error("The application could not load:\n%s", traceback.format_exc())
        return 1

    # Which database, and where that came from, without the password: the
    # first thing to know when the log fills with "password authentication failed".
    try:
        from sqlalchemy.engine import make_url

        url = make_url(settings.DATABASE_URL)
        where = f"{url.username}@{url.host}:{url.port}/{url.database}"
    except Exception:
        where = "(could not read DATABASE_URL)"
    if os.environ.get("DATABASE_URL"):
        log.warning(
            "DATABASE_URL is set as a Windows environment variable, so it is used instead of "
            "%s. Remove that variable unless you set it on purpose. Database: %s", ENV_FILE, where,
        )
    elif ENV_FILE.exists():
        log.info("Settings from %s. Database: %s", ENV_FILE, where)
    else:
        log.warning("%s is missing, so built-in defaults are used. Database: %s", ENV_FILE, where)

    # Bring the database up to date before serving. update.ps1 does this too,
    # but if it ever reached a different database (an old DATABASE_URL
    # variable did exactly that once) the server would start against tables
    # missing their new columns and fail screen by screen. This only ever adds
    # columns, so it is safe on every start; a failure is logged, not fatal.
    try:
        from app.core.database import engine
        from app.core.schema_update import add_missing_columns
        from app.models import Base

        Base.metadata.create_all(engine)
        added = add_missing_columns(engine)
        from app.core.schema_update import protect_audit_log
        protect_audit_log(engine)
        if added:
            log.info("Database brought up to date: %s", ", ".join(added))
        if "categories.earns_stamp" in added:
            from app.core.database import SessionLocal
            from app.seed import mark_stamp_categories

            with SessionLocal() as db:
                log.info("Earning stamps: %s", ", ".join(mark_stamp_categories(db)) or "no categories")
    except Exception as exc:
        log.warning("Could not check the database tables at start: %s", str(exc).splitlines()[0])

    # Uvicorn sets up logging afresh when it starts, which throws away any
    # handler added before that. So the file goes into its own configuration:
    # its messages, every request, and anything the application logs all land
    # in the same file as the lines above.
    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    config["formatters"]["plain"] = {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}
    config["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_FILE), "maxBytes": 1_000_000, "backupCount": 5,
        "encoding": "utf-8", "formatter": "plain",
    }
    for name in ("uvicorn", "uvicorn.access"):
        config["loggers"][name]["handlers"].append("file")
    config["root"] = {"handlers": ["file"], "level": "INFO"}

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info", log_config=config)
    except SystemExit as stop:
        if stop.code not in (0, None):
            log.error("The server stopped with code %s. If the port was taken, run scripts\\status.ps1.", stop.code)
        return int(stop.code or 0)
    except Exception:
        log.error("The server stopped:\n%s", traceback.format_exc())
        return 1
    log.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
