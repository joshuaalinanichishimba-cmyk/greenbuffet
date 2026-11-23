"""Writing to the audit log. Entries are added, never changed."""
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.access import AuditLog


def record(
    db: Session,
    actor: str,
    area: str,
    action: str,
    detail: str = "",
    reference: str = "",
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    def dump(v: Any) -> str | None:
        if v is None:
            return None
        return v if isinstance(v, str) else json.dumps(v, default=str)

    entry = AuditLog(
        at=datetime.now(timezone.utc),
        actor=actor,
        area=area,
        action=action,
        detail=detail[:300],
        reference=reference[:60],
        before=dump(before),
        after=dump(after),
    )
    db.add(entry)
    return entry
