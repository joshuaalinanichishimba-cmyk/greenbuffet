"""The books: chart of accounts, journal, ledger and the statements.

Every figure on every statement here is the sum of journal lines. Nothing is
stored twice and nothing is typed in by hand, so a statement cannot drift away
from the entries behind it.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import User
from app.models.books import ACCOUNT_TYPES, NORMAL_SIDE, Account, JournalEntry, JournalLine
from app.services.audit import record
from app.services.posting import Unbalanced, ensure_chart, post

router = APIRouter(prefix="/books", tags=["books"])

can_see = requires("books.view", "reports.view")
can_manage_accounts = requires("accounts.manage")
can_post = requires("journal.post", "books.edit")
can_approve = requires("journal.approve")

TYPE_LABELS = {
    "asset": "What we own",
    "liability": "What we owe",
    "equity": "Owner's stake",
    "income": "Money in",
    "expense": "Money out",
}


# ---------------------------------------------------------------------------
# shapes
# ---------------------------------------------------------------------------

class AccountIn(BaseModel):
    code: str = Field(min_length=3, max_length=12)
    name: str = Field(min_length=2, max_length=80)
    type: str
    description: str = Field(default="", max_length=200)
    is_cash: bool = False
    sort: int = Field(default=100, ge=0, le=9999)


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None
    sort: int | None = Field(default=None, ge=0, le=9999)


class AccountOut(BaseModel):
    id: str
    code: str
    name: str
    type: str
    type_label: str
    description: str
    is_system: bool
    is_active: bool
    is_cash: bool
    balance_ngwee: int


class LineIn(BaseModel):
    account_code: str
    debit_ngwee: int = Field(default=0, ge=0, le=1_000_000_000)
    credit_ngwee: int = Field(default=0, ge=0, le=1_000_000_000)
    memo: str = Field(default="", max_length=200)


class EntryIn(BaseModel):
    memo: str = Field(min_length=3, max_length=300)
    lines: list[LineIn] = Field(min_length=2)
    entry_date: date | None = None
    reference: str = Field(default="", max_length=40)


class LineOut(BaseModel):
    account_code: str
    account_name: str
    debit_ngwee: int
    credit_ngwee: int
    memo: str


class EntryOut(BaseModel):
    id: str
    number: str
    entry_date: str
    memo: str
    source: str
    reference: str
    status: str
    total_ngwee: int
    created_by: str | None
    approved_by: str | None
    reverses_id: str | None
    reversed_by_id: str | None
    lines: list[LineOut]


class LedgerRow(BaseModel):
    at: str
    entry_number: str
    memo: str
    reference: str
    debit_ngwee: int
    credit_ngwee: int
    balance_ngwee: int


class StatementRow(BaseModel):
    code: str
    name: str
    amount_ngwee: int


class ReverseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _balances(db: Session, upto: date | None = None, since: date | None = None) -> dict[str, int]:
    """Signed balance per account id: positive means the normal side."""
    stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit_ngwee), 0),
            func.coalesce(func.sum(JournalLine.credit_ngwee), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.status == "posted")
        .group_by(JournalLine.account_id)
    )
    if upto:
        stmt = stmt.where(JournalEntry.entry_date <= upto)
    if since:
        stmt = stmt.where(JournalEntry.entry_date >= since)

    types = {a.id: a.type for a in db.scalars(select(Account)).all()}
    out: dict[str, int] = {}
    for account_id, debit, credit in db.execute(stmt).all():
        side = NORMAL_SIDE.get(types.get(account_id, "asset"), "debit")
        out[account_id] = (debit - credit) if side == "debit" else (credit - debit)
    return out


def _entry_out(entry: JournalEntry) -> EntryOut:
    return EntryOut(
        id=entry.id, number=entry.number, entry_date=entry.entry_date.isoformat(),
        memo=entry.memo, source=entry.source, reference=entry.reference,
        status=entry.status, total_ngwee=entry.total_ngwee, created_by=entry.created_by,
        approved_by=entry.approved_by, reverses_id=entry.reverses_id,
        reversed_by_id=entry.reversed_by_id,
        lines=[
            LineOut(
                account_code=line.account.code, account_name=line.account.name,
                debit_ngwee=line.debit_ngwee, credit_ngwee=line.credit_ngwee, memo=line.memo,
            )
            for line in entry.lines
        ],
    )


def _month_bounds(month: str | None) -> tuple[date, date]:
    """'2026-11' or nothing, which means this month."""
    today = datetime.now(timezone.utc).date()
    if month:
        try:
            year, mon = (int(part) for part in month.split("-")[:2])
            start = date(year, mon, 1)
        except (ValueError, TypeError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use a month like 2026-11.")
    else:
        start = date(today.year, today.month, 1)
    end = date(start.year + (start.month == 12), (start.month % 12) + 1, 1) - timedelta(days=1)
    return start, end


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------

@router.get("/accounts", response_model=list[AccountOut])
def accounts(
    include_hidden: bool = False, db: Session = Depends(get_db), _: User = Depends(can_see),
):
    balances = _balances(db)
    stmt = select(Account).order_by(Account.sort, Account.code)
    if not include_hidden:
        stmt = stmt.where(Account.is_active.is_(True))
    return [
        AccountOut(
            id=a.id, code=a.code, name=a.name, type=a.type,
            type_label=TYPE_LABELS.get(a.type, a.type), description=a.description,
            is_system=a.is_system, is_active=a.is_active, is_cash=a.is_cash,
            balance_ngwee=balances.get(a.id, 0),
        )
        for a in db.scalars(stmt).all()
    ]


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, db: Session = Depends(get_db), user: User = Depends(can_manage_accounts)):
    if body.type not in ACCOUNT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Type must be one of: {', '.join(ACCOUNT_TYPES)}")
    code = body.code.strip()
    if db.scalar(select(Account).where(Account.code == code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That account code is already used.")
    account = Account(
        code=code, name=body.name.strip(), type=body.type, description=body.description.strip(),
        is_cash=body.is_cash, sort=body.sort, is_system=False, created_by=user.name,
    )
    db.add(account)
    record(db, user.name, "money", "Account added", f"{code} {account.name}", code)
    db.commit()
    db.refresh(account)
    return AccountOut(
        id=account.id, code=account.code, name=account.name, type=account.type,
        type_label=TYPE_LABELS.get(account.type, account.type), description=account.description,
        is_system=False, is_active=True, is_cash=account.is_cash, balance_ngwee=0,
    )


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def patch_account(
    account_id: str, body: AccountPatch,
    db: Session = Depends(get_db), user: User = Depends(can_manage_accounts),
):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
    if body.is_active is False:
        if account.is_system:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "The system posts to this account, so it cannot be switched off.",
            )
        used = db.scalar(select(func.count(JournalLine.id)).where(JournalLine.account_id == account.id)) or 0
        if used:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This account already has {used} entries and must stay for the record.",
            )
    if body.name:
        account.name = body.name.strip()
    if body.description is not None:
        account.description = body.description.strip()
    if body.sort is not None:
        account.sort = body.sort
    if body.is_active is not None:
        account.is_active = body.is_active
    record(db, user.name, "money", "Account changed", f"{account.code} {account.name}", account.code)
    db.commit()
    db.refresh(account)
    balances = _balances(db)
    return AccountOut(
        id=account.id, code=account.code, name=account.name, type=account.type,
        type_label=TYPE_LABELS.get(account.type, account.type), description=account.description,
        is_system=account.is_system, is_active=account.is_active, is_cash=account.is_cash,
        balance_ngwee=balances.get(account.id, 0),
    )


# ---------------------------------------------------------------------------
# the journal
# ---------------------------------------------------------------------------

@router.get("/journal", response_model=list[EntryOut])
def journal(
    source: str | None = None,
    month: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(can_see),
):
    stmt = select(JournalEntry).order_by(JournalEntry.entry_date.desc(), JournalEntry.number.desc()).limit(limit)
    if source:
        stmt = stmt.where(JournalEntry.source == source)
    if month:
        start, end = _month_bounds(month)
        stmt = stmt.where(JournalEntry.entry_date >= start, JournalEntry.entry_date <= end)
    return [_entry_out(e) for e in db.scalars(stmt).all()]


@router.post("/journal", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: EntryIn, db: Session = Depends(get_db), user: User = Depends(can_post)):
    """A hand-written entry: rent, a bank charge, an owner's contribution.

    It is written as a draft. Someone with approval rights posts it, so one
    person cannot both write and approve the same entry.
    """
    try:
        entry = post(
            db,
            [(l.account_code, l.debit_ngwee, l.credit_ngwee, l.memo.strip()) for l in body.lines],
            body.memo.strip(), source="manual", reference=body.reference.strip(),
            when=body.entry_date, who=user.name, status="draft",
        )
    except Unbalanced as problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(problem))
    record(db, user.name, "money", "Journal entry written", f"{entry.number}: {entry.memo}", entry.number)
    db.commit()
    db.refresh(entry)
    return _entry_out(entry)


@router.post("/journal/{entry_id}/approve", response_model=EntryOut)
def approve_entry(entry_id: str, db: Session = Depends(get_db), user: User = Depends(can_approve)):
    entry = db.get(JournalEntry, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found.")
    if entry.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft can be approved.")
    if entry.created_by == user.name:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An entry is approved by someone other than whoever wrote it.",
        )
    entry.status = "posted"
    entry.posted_at = datetime.now(timezone.utc)
    entry.posted_by = user.name
    entry.approved_at = entry.posted_at
    entry.approved_by = user.name
    record(db, user.name, "money", "Journal entry approved", f"{entry.number}: {entry.memo}", entry.number)
    db.commit()
    db.refresh(entry)
    return _entry_out(entry)


@router.post("/journal/{entry_id}/reverse", response_model=EntryOut)
def reverse_entry(
    entry_id: str, body: ReverseIn, db: Session = Depends(get_db), user: User = Depends(can_approve),
):
    """Undoes a posted entry by writing its mirror. Neither one is deleted."""
    entry = db.get(JournalEntry, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found.")
    if entry.status != "posted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a posted entry can be reversed.")
    if entry.reversed_by_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That entry has already been reversed.")
    if entry.reverses_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That entry is itself a reversal.")

    mirrored = [
        (line.account.code, line.credit_ngwee, line.debit_ngwee, f"Reversal: {line.memo}".strip())
        for line in entry.lines
    ]
    reversal = post(
        db, mirrored, f"Reverses {entry.number}: {body.reason.strip()}",
        source=entry.source, reference=entry.reference, who=user.name,
    )
    reversal.reverses_id = entry.id
    # The original stays posted. Both entries count, and together they come to
    # nothing — which is what a reversal means. Dropping the original would
    # leave its mirror standing alone and move every statement by its value.
    entry.reversed_by_id = reversal.id
    entry.note = (entry.note + "\n" if entry.note else "") + f"Reversed by {user.name}: {body.reason.strip()}"
    record(db, user.name, "money", "Journal entry reversed", f"{entry.number}: {body.reason.strip()}", entry.number)
    db.commit()
    db.refresh(reversal)
    return _entry_out(reversal)


@router.get("/ledger/{code}", response_model=list[LedgerRow])
def ledger(
    code: str, limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db), _: User = Depends(can_see),
):
    account = db.scalar(select(Account).where(Account.code == code))
    if not account:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
    rows = db.execute(
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.account_id == account.id, JournalEntry.status == "posted")
        .order_by(JournalEntry.entry_date, JournalEntry.number)
        .limit(limit)
    ).all()
    side = NORMAL_SIDE[account.type]
    running = 0
    out: list[LedgerRow] = []
    for line, entry in rows:
        running += (line.debit_ngwee - line.credit_ngwee) if side == "debit" else (line.credit_ngwee - line.debit_ngwee)
        out.append(LedgerRow(
            at=entry.entry_date.isoformat(), entry_number=entry.number,
            memo=line.memo or entry.memo, reference=entry.reference,
            debit_ngwee=line.debit_ngwee, credit_ngwee=line.credit_ngwee, balance_ngwee=running,
        ))
    out.reverse()
    return out


# ---------------------------------------------------------------------------
# statements
# ---------------------------------------------------------------------------

@router.get("/trial-balance")
def trial_balance(month: str | None = None, db: Session = Depends(get_db), _: User = Depends(can_see)):
    """Every account with a balance, and the proof that the books balance."""
    _, end = _month_bounds(month)
    raw = db.execute(
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit_ngwee), 0),
            func.coalesce(func.sum(JournalLine.credit_ngwee), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.status == "posted", JournalEntry.entry_date <= end)
        .group_by(JournalLine.account_id)
    ).all()
    accounts_by_id = {a.id: a for a in db.scalars(select(Account)).all()}
    rows = []
    total_debit = total_credit = 0
    for account_id, debit, credit in raw:
        account = accounts_by_id.get(account_id)
        if not account:
            continue
        net = debit - credit
        d = net if net > 0 else 0
        c = -net if net < 0 else 0
        if d == 0 and c == 0:
            continue
        total_debit += d
        total_credit += c
        rows.append({
            "code": account.code, "name": account.name, "type": account.type,
            "debit_ngwee": d, "credit_ngwee": c,
        })
    rows.sort(key=lambda r: r["code"])
    return {
        "as_at": end.isoformat(),
        "rows": rows,
        "total_debit_ngwee": total_debit,
        "total_credit_ngwee": total_credit,
        "balanced": total_debit == total_credit,
    }


@router.get("/profit-and-loss")
def profit_and_loss(month: str | None = None, db: Session = Depends(get_db), _: User = Depends(can_see)):
    start, end = _month_bounds(month)
    balances = _balances(db, upto=end, since=start)
    accounts_by_id = {a.id: a for a in db.scalars(select(Account)).all()}

    income: list[StatementRow] = []
    cost_of_sales: list[StatementRow] = []
    expenses: list[StatementRow] = []
    for account_id, amount in balances.items():
        account = accounts_by_id.get(account_id)
        if not account or amount == 0:
            continue
        row = StatementRow(code=account.code, name=account.name, amount_ngwee=amount)
        if account.type == "income":
            income.append(row)
        elif account.type == "expense" and account.code.startswith("5"):
            cost_of_sales.append(row)
        elif account.type == "expense":
            expenses.append(row)

    for group in (income, cost_of_sales, expenses):
        group.sort(key=lambda r: r.code)
    total_income = sum(r.amount_ngwee for r in income)
    total_cost = sum(r.amount_ngwee for r in cost_of_sales)
    total_expenses = sum(r.amount_ngwee for r in expenses)
    gross = total_income - total_cost
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "income": [r.model_dump() for r in income],
        "total_income_ngwee": total_income,
        "cost_of_sales": [r.model_dump() for r in cost_of_sales],
        "total_cost_of_sales_ngwee": total_cost,
        "gross_profit_ngwee": gross,
        "gross_margin_percent": round(gross / total_income * 100, 1) if total_income else 0,
        "expenses": [r.model_dump() for r in expenses],
        "total_expenses_ngwee": total_expenses,
        "profit_ngwee": gross - total_expenses,
    }


@router.get("/balance-sheet")
def balance_sheet(month: str | None = None, db: Session = Depends(get_db), _: User = Depends(can_see)):
    _, end = _month_bounds(month)
    balances = _balances(db, upto=end)
    accounts_by_id = {a.id: a for a in db.scalars(select(Account)).all()}

    assets: list[StatementRow] = []
    liabilities: list[StatementRow] = []
    equity: list[StatementRow] = []
    profit = 0
    for account_id, amount in balances.items():
        account = accounts_by_id.get(account_id)
        if not account or amount == 0:
            continue
        row = StatementRow(code=account.code, name=account.name, amount_ngwee=amount)
        if account.type == "asset":
            assets.append(row)
        elif account.type == "liability":
            liabilities.append(row)
        elif account.type == "equity":
            equity.append(row)
        elif account.type == "income":
            profit += amount
        elif account.type == "expense":
            profit -= amount

    for group in (assets, liabilities, equity):
        group.sort(key=lambda r: r.code)
    total_assets = sum(r.amount_ngwee for r in assets)
    total_liabilities = sum(r.amount_ngwee for r in liabilities)
    total_equity = sum(r.amount_ngwee for r in equity) + profit
    return {
        "as_at": end.isoformat(),
        "assets": [r.model_dump() for r in assets],
        "total_assets_ngwee": total_assets,
        "liabilities": [r.model_dump() for r in liabilities],
        "total_liabilities_ngwee": total_liabilities,
        "equity": [r.model_dump() for r in equity],
        "profit_this_period_ngwee": profit,
        "total_equity_ngwee": total_equity,
        # Assets = what we owe + what is ours. If this is false, something is wrong.
        "balanced": total_assets == total_liabilities + total_equity,
        "difference_ngwee": total_assets - (total_liabilities + total_equity),
    }


@router.get("/cash-flow")
def cash_flow(month: str | None = None, db: Session = Depends(get_db), _: User = Depends(can_see)):
    """Money in and out of the accounts that hold real money."""
    start, end = _month_bounds(month)
    cash_accounts = {a.id: a for a in db.scalars(select(Account).where(Account.is_cash.is_(True))).all()}
    if not cash_accounts:
        return {"from": start.isoformat(), "to": end.isoformat(), "accounts": [], "opening_ngwee": 0,
                "in_ngwee": 0, "out_ngwee": 0, "closing_ngwee": 0}

    opening = _balances(db, upto=start - timedelta(days=1))
    rows = db.execute(
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit_ngwee), 0),
            func.coalesce(func.sum(JournalLine.credit_ngwee), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= start,
            JournalEntry.entry_date <= end,
            JournalLine.account_id.in_(list(cash_accounts)),
        )
        .group_by(JournalLine.account_id)
    ).all()

    out_rows = []
    total_in = total_out = total_open = 0
    moved = {account_id: (d, c) for account_id, d, c in rows}
    for account_id, account in cash_accounts.items():
        came_in, went_out = moved.get(account_id, (0, 0))
        open_balance = opening.get(account_id, 0)
        total_in += came_in
        total_out += went_out
        total_open += open_balance
        if not (came_in or went_out or open_balance):
            continue
        out_rows.append({
            "code": account.code, "name": account.name,
            "opening_ngwee": open_balance, "in_ngwee": came_in, "out_ngwee": went_out,
            "closing_ngwee": open_balance + came_in - went_out,
        })
    out_rows.sort(key=lambda r: r["code"])
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "accounts": out_rows,
        "opening_ngwee": total_open,
        "in_ngwee": total_in,
        "out_ngwee": total_out,
        "closing_ngwee": total_open + total_in - total_out,
    }


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup_chart(db: Session = Depends(get_db), user: User = Depends(can_manage_accounts)):
    """Creates any missing account from the standard chart."""
    made = ensure_chart(db)
    if made:
        record(db, user.name, "money", "Chart of accounts set up", f"{made} accounts added")
    db.commit()
    return {"added": made}
