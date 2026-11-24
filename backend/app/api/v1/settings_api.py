"""Business settings, files and backups.

Settings are rows, not code, so the restaurant's name, address, VAT number and
receipt footer can change without a new release — and the receipt reads them
rather than carrying them in Python.
"""
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as config
from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import Setting, User
from app.models.files import ATTACH_TO, KINDS, Document
from app.services.audit import record

router = APIRouter(prefix="/settings", tags=["settings"])

can_see = requires(
    "settings.edit", "menu.edit", "books.view", "hr.view", "purchases.manage", "pos.use",
)
can_edit = requires("settings.edit")

# Anyone who serves customers needs the dish photographs. Everything else — a
# supplier contract, an employee's certificate, an invoice — is only for the
# people whose work involves it.
DOCUMENT_READERS = {"settings.edit", "books.view", "hr.view", "hr.manage", "purchases.manage"}


def _sees_all_documents(user: User) -> bool:
    return bool(DOCUMENT_READERS & set(user.role.permission_codes))


def _is_dish_photo(doc: Document) -> bool:
    return doc.attached_to == "product" and doc.kind == "photo"
LUSAKA = timezone(timedelta(hours=2))

# backend/uploads, next to the code and inside what the backup script copies.
UPLOADS = Path(__file__).resolve().parents[3] / "uploads"
BACKUPS = Path(__file__).resolve().parents[3].parent / "backups"

MAX_BYTES = 8 * 1024 * 1024
ALLOWED = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "application/pdf": ".pdf",
}

BUSINESS_KEYS = {
    "business_name": "The Green Buffet",
    "business_address": "Liberty Mall, Kitwe",
    "business_phone": "0960554543 / 0972699005",
    "business_email": "",
    "business_tpin": "",
    "business_vat_number": "",
    "vat_rate": "16",
    "receipt_footer": "Thank you. Prices include VAT.",
    "service_note": "",
    # The demo's Settings screen: social handle, WhatsApp line, the topping
    # charge, the kitchen's base time, the stamp card, and opening hours.
    "business.social": "@the.green.buffet",
    "business.whatsapp": "0960554543",
    "menu.topping_charge_ngwee": "1000",
    "service.prep_minutes": "12",
    "loyalty.enabled": "true",
    "loyalty.stamps_needed": "8",
    # The sign-in screen lists each kind of account's people, so a tap fills
    # the email in, as the demo's account cards do. Turn off to show only the
    # kinds of account and make everyone type their email.
    "signin.show_accounts": "true",
    # Tax: registered for VAT at 16% inside the price, as the owners confirmed
    # (24 Nov 2026). Either owner can change it at any time; new sales follow,
    # past sales keep the VAT they were sold with.
    "tax.vat_registered": "true",
    # Cash controls at the till (stage 22). A till that counts out by more
    # than the variance limit needs a reason and a manager's review; a
    # cashier's discount above the percentage needs a manager's approval.
    "till.variance_limit_ngwee": "2000",
    "till.discount_limit_percent": "10",
    "hours.sun": "08:30-15:00",
    "hours.mon": "08:30-19:30",
    "hours.tue": "08:30-19:30",
    "hours.wed": "08:30-19:30",
    "hours.thu": "08:30-19:30",
    "hours.fri": "08:30-19:30",
    "hours.sat": "08:30-19:30",
}

# Numbers that must stay numbers, with the range that makes sense for each.
WHOLE_NUMBERS = {
    "service.prep_minutes": (1, 120),
    "loyalty.stamps_needed": (1, 50),
    "menu.topping_charge_ngwee": (0, 100_000),
    "till.variance_limit_ngwee": (0, 10_000_000),
    "till.discount_limit_percent": (0, 100),
}


class SettingsOut(BaseModel):
    values: dict[str, str]


class SettingsIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class DocumentOut(BaseModel):
    id: str
    name: str
    kind: str
    attached_to: str
    attached_id: str | None
    media_type: str
    size_bytes: int
    note: str
    is_primary: bool
    at: str
    by: str | None
    url: str
    thumb_url: str | None


class BackupOut(BaseModel):
    name: str
    size_bytes: int
    at: str


def business_settings(db: Session) -> dict[str, str]:
    stored = {s.key: s.value for s in db.scalars(select(Setting)).all()}
    return {key: stored.get(key, fallback) for key, fallback in BUSINESS_KEYS.items()}


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

@router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db), _: User = Depends(can_see)):
    return SettingsOut(values=business_settings(db))


@router.put("", response_model=SettingsOut)
def write_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    unknown = [k for k in body.values if k not in BUSINESS_KEYS]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown setting: {unknown[0]}")
    if "vat_rate" in body.values:
        try:
            rate = float(body.values["vat_rate"])
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The VAT rate must be a number.")
        if not 0 <= rate <= 100:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The VAT rate must be between 0 and 100.")
    if "business_name" in body.values and len(body.values["business_name"].strip()) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The business needs a name.")
    # Only settings something reads. A misspelt key would otherwise be saved,
    # shown nowhere, and leave the real setting unchanged without a word.
    unknown = sorted(set(body.values) - set(BUSINESS_KEYS))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown setting: {', '.join(unknown)}.")
    for key, (low, high) in WHOLE_NUMBERS.items():
        if key in body.values:
            try:
                number = int(body.values[key].strip())
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key} must be a whole number.")
            if not low <= number <= high:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key} must be between {low} and {high}.")
    if "business_tpin" in body.values and body.values["business_tpin"].strip() \
            and not body.values["business_tpin"].strip().isdigit():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A TPIN is digits only.")
    for flag in ("loyalty.enabled", "signin.show_accounts", "tax.vat_registered"):
        if flag in body.values and body.values[flag] not in ("true", "false"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{flag} must be true or false.")

    before = business_settings(db)
    for key, value in body.values.items():
        row = db.get(Setting, key)
        if row:
            row.value = value.strip()
        else:
            db.add(Setting(key=key, value=value.strip()))
    db.flush()
    after = business_settings(db)
    changed = {k: (before[k], after[k]) for k in after if before.get(k) != after[k]}
    # The demo's "charge per topping over five" lives on the menu's topping
    # choices; changing it here changes it there, so the two never disagree.
    if "menu.topping_charge_ngwee" in changed:
        from app.models.menu import OptionGroup
        for group in db.scalars(select(OptionGroup).where(OptionGroup.free_count > 0)).all():
            group.extra_ngwee = int(after["menu.topping_charge_ngwee"])
    if changed:
        record(db, user.name, "settings", "Settings changed", ", ".join(changed),
               before=json.dumps({k: v[0] for k, v in changed.items()}),
               after=json.dumps({k: v[1] for k, v in changed.items()}))
    db.commit()
    return SettingsOut(values=after)


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

def _url(doc: Document) -> str:
    return f"/api/v1/settings/files/{doc.id}"


def _doc_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id, name=doc.name, kind=doc.kind, attached_to=doc.attached_to,
        attached_id=doc.attached_id, media_type=doc.media_type, size_bytes=doc.size_bytes,
        note=doc.note, is_primary=doc.is_primary, at=doc.created_at.isoformat(),
        by=doc.created_by, url=_url(doc),
        thumb_url=f"{_url(doc)}?thumb=true" if doc.thumb_path else None,
    )


@router.get("/files", response_model=list[DocumentOut])
def files(
    attached_to: str | None = None,
    attached_id: str | None = None,
    kind: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(can_see),
):
    stmt = select(Document).order_by(Document.created_at.desc())
    if not _sees_all_documents(user):
        # A cashier sees the dishes, not the paperwork.
        stmt = stmt.where(Document.attached_to == "product", Document.kind == "photo")
    if attached_to:
        stmt = stmt.where(Document.attached_to == attached_to)
    if attached_id:
        stmt = stmt.where(Document.attached_id == attached_id)
    if kind:
        stmt = stmt.where(Document.kind == kind)
    return [_doc_out(d) for d in db.scalars(stmt).all()]


@router.post("/files", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    kind: str = Form("other"),
    attached_to: str = Form("other"),
    attached_id: str = Form(""),
    note: str = Form(""),
    is_primary: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(requires("settings.edit", "menu.edit", "hr.manage", "purchases.manage")),
):
    if kind not in KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Kind must be one of: {', '.join(KINDS)}")
    if attached_to not in ATTACH_TO:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown thing to attach this to.")
    if file.content_type not in ALLOWED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Only JPEG, PNG, WebP images and PDF files can be stored.",
        )

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That file is {len(content) // 1024 // 1024} MB. The limit is 8 MB.",
        )
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That file is empty.")

    safe_name = "".join(
        c for c in (file.filename or "file") if c.isalnum() or c in " .,-_()[]&+"
    ).strip()[:160] or "file"
    doc = Document(
        name=safe_name, kind=kind, attached_to=attached_to,
        attached_id=attached_id or None, media_type=file.content_type,
        size_bytes=len(content), note=note.strip()[:300], created_by=user.name, path="",
    )
    folder = UPLOADS / attached_to
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{doc.id}{ALLOWED[file.content_type]}"
    (folder / name).write_bytes(content)
    doc.path = f"{attached_to}/{name}"

    # A photograph gets a small copy, so a list of dishes does not pull
    # several megabytes over the counter's wifi.
    if file.content_type.startswith("image/"):
        try:
            from io import BytesIO

            from PIL import Image

            image = Image.open(BytesIO(content))
            image.thumbnail((480, 480))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            thumb_name = f"{doc.id}-small.jpg"
            image.save(folder / thumb_name, "JPEG", quality=82)
            doc.thumb_path = f"{attached_to}/{thumb_name}"
        except Exception:
            # A thumbnail is a convenience; the original is what matters.
            doc.thumb_path = None

    if is_primary and attached_id:
        for other in db.scalars(
            select(Document).where(
                Document.attached_to == attached_to, Document.attached_id == attached_id,
                Document.is_primary.is_(True),
            )
        ).all():
            other.is_primary = False
        doc.is_primary = True

    db.add(doc)
    record(db, user.name, "settings", "File stored", f"{doc.name} ({kind})", attached_id or attached_to)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


@router.get("/files/{file_id}")
def read_file(
    file_id: str, thumb: bool = Query(default=False),
    db: Session = Depends(get_db), user: User = Depends(can_see),
):
    doc = db.get(Document, file_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    if not _is_dish_photo(doc) and not _sees_all_documents(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{user.role.label} accounts cannot open this file.")
    relative = doc.thumb_path if (thumb and doc.thumb_path) else doc.path
    full = UPLOADS / relative
    # Never let a stored path reach outside the uploads folder.
    if not full.resolve().is_relative_to(UPLOADS.resolve()) or not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That file is no longer on disk.")
    media = "image/jpeg" if (thumb and doc.thumb_path) else doc.media_type
    return FileResponse(full, media_type=media, filename=doc.name)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: str, db: Session = Depends(get_db),
    user: User = Depends(requires("settings.edit", "menu.edit", "hr.manage")),
):
    doc = db.get(Document, file_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    for relative in (doc.path, doc.thumb_path):
        if not relative:
            continue
        full = UPLOADS / relative
        if full.exists() and full.resolve().is_relative_to(UPLOADS.resolve()):
            full.unlink()
    record(db, user.name, "settings", "File removed", doc.name, doc.attached_id or doc.attached_to)
    db.delete(doc)
    db.commit()


# ---------------------------------------------------------------------------
# backups
# ---------------------------------------------------------------------------

@router.get("/backups", response_model=list[BackupOut])
def backups(_: User = Depends(can_edit)):
    if not BACKUPS.exists():
        return []
    rows = []
    for item in sorted(BACKUPS.glob("*.dump"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = item.stat()
        rows.append(BackupOut(
            name=item.name, size_bytes=stat.st_size,
            at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone(LUSAKA).isoformat(),
        ))
    return rows[:40]


@router.post("/backups", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
def make_backup(db: Session = Depends(get_db), user: User = Depends(can_edit)):
    """Runs pg_dump into the backups folder, the same file the scripts make."""
    url = config.DATABASE_URL
    try:
        rest = url.split("://", 1)[1]
        credentials, hostpart = rest.split("@", 1)
        username, password = credentials.split(":", 1)
        host_port, database = hostpart.split("/", 1)
        host, _, port = host_port.partition(":")
    except (IndexError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The database address could not be read.")

    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(LUSAKA).strftime("%Y%m%d-%H%M%S")
    target = BACKUPS / f"greenbuffet-{stamp}.dump"
    tool = shutil.which("pg_dump")
    if not tool:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "pg_dump is not on the PATH. Use .\\scripts\\backup.ps1 instead, which finds it.",
        )
    environment = {**os.environ, "PGPASSWORD": password}
    result = subprocess.run(
        [tool, "-h", host or "localhost", "-p", port or "5432", "-U", username,
         "-F", "c", "-f", str(target), database.split("?")[0]],
        capture_output=True, text=True, env=environment, timeout=600,
    )
    if result.returncode != 0 or not target.exists():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"The backup failed: {(result.stderr or '').strip()[:200]}",
        )
    record(db, user.name, "settings", "Backup taken", target.name)
    db.commit()
    stat = target.stat()
    return BackupOut(
        name=target.name, size_bytes=stat.st_size,
        at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone(LUSAKA).isoformat(),
    )
