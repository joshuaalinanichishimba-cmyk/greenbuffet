"""Fail closed unless integration tests use the isolated test stack."""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url


def validate_test_target() -> None:
    from app.core.config import settings

    problems: list[str] = []
    if os.environ.get("GB_TEST_MODE") != "1":
        problems.append("GB_TEST_MODE=1 is required")
    if settings.ENVIRONMENT != "test":
        problems.append("ENVIRONMENT must be test")
    try:
        db = make_url(settings.DATABASE_URL)
        if db.get_backend_name() != "postgresql":
            problems.append("DATABASE_URL must point to PostgreSQL")
        if not db.host or not ipaddress.ip_address(db.host).is_loopback:
            problems.append("DATABASE_URL must use a loopback host")
        if not (db.database or "").startswith("greenbuffet_test_"):
            problems.append("database name must start with greenbuffet_test_")
        if not (db.username or "").startswith("gb_app_"):
            problems.append("DATABASE_URL must use the isolated gb_app_ test role")
        if db.port != 55432:
            problems.append("DATABASE_URL must use the isolated test PostgreSQL port 55432")
    except (ValueError, TypeError):
        problems.append("DATABASE_URL is not a local test database URL")

    base = urlsplit(os.environ.get("GB_BASE", ""))
    if (base.scheme != "http" or base.hostname not in {"127.0.0.1", "::1"}
            or base.port != 18000 or not base.path.rstrip("/").endswith("/api/v1")):
        problems.append("GB_BASE must target http://127.0.0.1:18000/api/v1")
    if settings.EMAIL_MODE != "file" or not settings.EMAIL_FILE_DIR:
        problems.append("email must be captured with EMAIL_MODE=file and EMAIL_FILE_DIR")

    live_payment_keys = [key for key, value in os.environ.items()
                         if value and any(part in key.upper() for part in
                                          ("LENCO", "PAYMENT", "AIRTEL", "MTN", "ZAMTEL", "MOMO"))]
    if live_payment_keys:
        problems.append("payment-provider environment variables must be unset")
    if problems:
        raise RuntimeError("Unsafe test target: " + "; ".join(problems))
