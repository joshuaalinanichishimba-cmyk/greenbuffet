"""Database engine and session handling."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# A restaurant at lunch has several tills, the kitchen board and a manager's
# dashboard all talking at once. The default pool of five is too small for
# that: requests queue behind each other and the till feels slow.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one database session per request.

    The session is rolled back and closed even if the endpoint raises, so a
    half-finished sale can never be left committed.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
