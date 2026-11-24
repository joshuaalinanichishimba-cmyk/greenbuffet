"""Health and version endpoints, used by the setup script and by monitoring.

The health check has to answer even when the database is down, because that
is exactly when someone is asking it. It used to fail with a server error and
a traceback; now it says in plain words what is wrong, with a 503 so scripts
can still tell it apart from a working system.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    body = {
        "status": "ok",
        "database": "connected",
        "environment": settings.ENVIRONMENT,
        "business": settings.BUSINESS_NAME,
    }
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        body["status"] = "degraded"
        body["database"] = "unreachable"
        if "password authentication failed" in str(exc):
            # PostgreSQL is up; it just refuses the password in backend\.env.
            body["reason"] = "password"
            body["detail"] = (
                "PostgreSQL is running but refused the database password in backend\\.env. "
                "Run scripts\\fix-database.ps1 on the server computer."
            )
        else:
            body["reason"] = "not_running"
            body["detail"] = (
                "The server is running but cannot reach PostgreSQL. On Windows, check that the "
                "postgresql service is running (services.msc), then try again."
            )
        return JSONResponse(body, status_code=503)
    return body
