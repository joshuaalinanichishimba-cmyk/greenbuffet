"""The Green Buffet management system: FastAPI application entry point.

Run from the backend/ folder:
    uvicorn app.main:app --reload
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.frontend import PosFrontend

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("greenbuffet")

app = FastAPI(
    title="The Green Buffet management system",
    version="1.0.0-stage12",
    description="Ordering, kitchen, inventory, accounting, HR and payroll for The Green Buffet.",
    docs_url="/docs",
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


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace to the browser; log it instead."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong. The error has been logged."},
    )


@app.middleware("http")
async def security_headers(request, call_next):
    """Headers that cost nothing and close off whole classes of attack."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.ENVIRONMENT != "development" and request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(api_router)


if settings.POS_FRONTEND_DIR is not None:
    if len(settings.JWT_SECRET) < 32:
        raise RuntimeError("Set a randomly generated JWT_SECRET of at least 32 characters in backend/.env.")
    if not (settings.POS_FRONTEND_DIR / "index.html").is_file():
        raise RuntimeError("POS_FRONTEND_DIR must point to the built Vue app.")
    app.mount("/", PosFrontend(directory=settings.POS_FRONTEND_DIR, html=True))
else:
    @app.get("/")
    def root() -> dict:
        return {
            "name": "The Green Buffet management system",
            "stage": 12,
            "docs": "/docs",
            "health": "/api/v1/health",
        }
