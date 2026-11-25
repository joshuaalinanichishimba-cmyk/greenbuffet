"""The Green Buffet management system: FastAPI application entry point.

Run from the backend/ folder:
    uvicorn app.main:app --reload
"""
import logging
import uuid
from pathlib import Path

from sqlalchemy.exc import OperationalError
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("greenbuffet")

app = FastAPI(
    title="The Green Buffet management system",
    version="1.0.0",
    description="Ordering, kitchen, inventory, accounting, HR and payroll for The Green Buffet.",
    # The interactive API documentation is a development convenience. In
    # service it is one more thing to attack, and nobody at the restaurant
    # needs it.
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    # The browser cannot read the filename on a download unless it is exposed.
    expose_headers=["Content-Disposition"],
    allow_headers=["*"],
)


@app.exception_handler(OperationalError)
async def database_down(request: Request, exc: OperationalError) -> JSONResponse:
    """The database is not answering: say so, instead of a vague error."""
    log.error("Database not reachable on %s %s: %s", request.method, request.url.path,
              str(exc).splitlines()[0] if str(exc) else exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The system cannot reach its database. On the server computer, "
                           "run scripts\\status.ps1 to see why."},
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace to the browser; log it instead."""
    # A short reference ties a screenshot of the message to its full entry in
    # logs\\server.log, so nobody has to guess which of the day's errors it was.
    ref = uuid.uuid4().hex[:6]
    log.exception("Unhandled error [ref %s] on %s %s", ref, request.method, request.url.path)
    # Also into the IT workspace's error log, grouped with earlier repeats.
    try:
        from app.core.database import SessionLocal
        from app.services.ops import record_error
        with SessionLocal() as db:
            record_error(db, exc, request.url.path, request.method, ref)
            db.commit()
    except Exception:
        log.exception("Could not write the error to the error log")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Something went wrong (reference {ref}, {type(exc).__name__}). "
                           "The details are in logs\\server.log on the server computer."},
    )


# On the online demo anyone can sign in as anyone, so the few things that
# would lock other visitors out, or leave the demo broken for the next one,
# are switched off there. Everything else works, sales included.
DEMO_BLOCKED = (
    ("POST", "/api/v1/auth/change-password"), ("POST", "/api/v1/auth/two-step/"),
    ("POST", "/api/v1/admin/users"), ("PATCH", "/api/v1/admin/users/"), ("PUT", "/api/v1/admin/roles/"),
    ("POST", "/api/v1/team/"), ("DELETE", "/api/v1/"),
    ("PUT", "/api/v1/settings"), ("POST", "/api/v1/settings/backups"), ("POST", "/api/v1/profile/me/photo"),
)


# Paths that keep working in read-only mode and while orders are stopped:
# signing in and out, the heartbeat, notices, problem reports and the IT
# workspace itself, so the people fixing a fault can still work.
ALWAYS_OPEN = ("/api/v1/auth/", "/api/v1/presence/", "/api/v1/notifications", "/api/v1/it/",
               "/api/v1/tickets", "/api/v1/profile/me")


def _client_ip(request) -> str:
    return request.client.host if request.client else ""


@app.middleware("http")
async def controls_and_limits(request, call_next):
    """Rate limits and the emergency controls, before any route runs."""
    from fastapi.responses import JSONResponse
    from app.services.ops import LIMITS, limiter

    path, method = request.url.path, request.method
    for prefix, only, count, seconds in LIMITS:
        if path.startswith(prefix) and (only is None or only == method):
            # Per address, plus the signed-in token when there is one, so a
            # whole restaurant behind one mobile router is not one bucket.
            who = _client_ip(request) + "|" + request.headers.get("authorization", "")[-16:]
            if not limiter.allow(f"{prefix}|{who}", count, seconds):
                try:
                    from app.core.database import SessionLocal
                    from app.services.ops import security_event
                    with SessionLocal() as db:
                        security_event(db, "rate_limited", "medium", f"Over {count} requests in {seconds}s",
                                       ip=_client_ip(request), path=path)
                        db.commit()
                except Exception:
                    pass
                return JSONResponse(status_code=429, content={
                    "detail": "Too many requests in a short time. Wait a minute and try again."})
            break

    if method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/api/v1/") and not path.startswith(ALWAYS_OPEN):
        from app.core.database import SessionLocal
        from app.services.ops import control
        try:
            with SessionLocal() as db:
                read_only = control(db, "read_only")
                taking = control(db, "take_orders")
        except Exception:
            read_only, taking = False, True
        if read_only or (not taking and path == "/api/v1/sales/orders" and method == "POST"):
            role = ""
            from app.core.security import decode_token
            header = request.headers.get("authorization", "")
            claims = decode_token(header[7:]) if header.lower().startswith("bearer ") else None
            role = (claims or {}).get("role", "")
            if read_only and role not in ("owner", "it"):
                return JSONResponse(status_code=503, content={
                    "detail": "The system is in read-only mode while a problem is fixed. You can look, "
                              "but nothing can be changed yet. Ask the owner or IT how long it will be."})
            if not taking and path == "/api/v1/sales/orders":
                return JSONResponse(status_code=503, content={
                    "detail": "New orders are stopped for now. The kitchen is finishing the orders it has."})
    return await call_next(request)


@app.middleware("http")
async def demo_guard(request, call_next):
    if settings.ENVIRONMENT == "demo":
        path, method = request.url.path, request.method
        if any(method == m and path.startswith(p) for m, p in DEMO_BLOCKED):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={
                "detail": "Switched off in the online demo, so the next visitor finds it as you did. "
                          "It works in the restaurant's own system."})
    return await call_next(request)


@app.middleware("http")
async def security_headers(request, call_next):
    """Headers that cost nothing and close off whole classes of attack."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Only this site's own scripts run. Styles may be inline (the screens set
    # widths and colours on elements); images may be data: or blob: (photos
    # are fetched with the sign-in token and shown from memory).
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
        "object-src 'none'; manifest-src 'self'; worker-src 'self'"
    )
    if settings.ENVIRONMENT != "development":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(api_router)

# In service, the built front end is served by this same process at the same
# address, so a phone or a kitchen tablet needs one URL and no CORS at all.
# In development the Vite server runs separately and this folder is absent.
BUILT = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if BUILT.is_dir():
    app.mount("/assets", StaticFiles(directory=BUILT / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def serve_the_app(path: str):
        """Anything that is not the API is a page of the front end.

        The app routes in the browser, so /till and /books must each return
        index.html rather than 404 — otherwise a refresh on any page breaks.
        """
        # An API path that reached here is one that does not exist. Handing
        # back the front end with a 200 hides the mistake: a script asking for
        # a route that was renamed gets a page of HTML and reports success.
        # It has to be an honest 404, in the shape the rest of the API uses.
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such endpoint.")
        candidate = (BUILT / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(BUILT.resolve()):
            return FileResponse(candidate)
        return FileResponse(BUILT / "index.html")


@app.get("/")
def root() -> dict:
    return {
        "name": "The Green Buffet management system",
        "stage": 1,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
