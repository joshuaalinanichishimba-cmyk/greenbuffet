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
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Something went wrong (reference {ref}, {type(exc).__name__}). "
                           "The details are in logs\\server.log on the server computer."},
    )


@app.middleware("http")
async def security_headers(request, call_next):
    """Headers that cost nothing and close off whole classes of attack."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
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
