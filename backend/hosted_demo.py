"""Vercel ASGI entrypoint for the demonstration on its own database."""
from app.core.config import settings
from app.main import app  # noqa: F401

if not settings.hosted_demo:
    raise RuntimeError("The hosted app requires DEMO_ENABLED=true and ENVIRONMENT=production.")
if len(settings.JWT_SECRET) < 32 or settings.JWT_SECRET == "replace-with-a-long-random-secret":
    raise RuntimeError("Set a generated JWT_SECRET for the hosted demo.")
