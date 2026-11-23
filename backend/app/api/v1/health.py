"""Health and version endpoints, used by the setup script and by monitoring."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "connected",
        "environment": settings.ENVIRONMENT,
        "business": settings.BUSINESS_NAME,
    }
