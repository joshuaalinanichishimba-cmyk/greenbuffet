"""Writing to the books.

Everything that reaches the ledger goes through `post()`, which refuses an
entry whose debits and credits do not match. That single check is what keeps
the trial balance at zero no matter what else happens in the system.

The chart of accounts below is a small restaurant's: enough to keep real books
without asking an owner to design one. Accounts can be added in the app; the
ones marked system are the ones these rules post to by code.
"""
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.books import Account, JournalEntry, JournalLine
from app.services.numbering import numbered

# code, name, type, is_cash, sort, description
CHART: list[tuple[str, str, str, bool, int, str]] = [
    ("1000", "Cash in the drawer", "asset", True, 10, "Notes and coins at the till"),
    ("1010", "Bank account", "asset", True, 20, "The business bank account"),
    ("1020", "Airtel Money", "asset", True, 30, "Collected on the Airtel merchant line"),
    ("1030", "MTN MoMo", "asset", True, 40, "Collected on the MTN merchant line"),
    ("1040", "Zamtel Kwacha", "asset", True, 50, "Collected on the Zamtel merchant line"),
    ("1050", "Card settlements", "asset", True, 60, "Card takings before the bank settles them"),
    ("1100", "Money owed to us", "asset", False, 70, "Customers buying on account"),
    ("1200", "Stock on hand", "asset", False, 80, "Ingredients in the store room"),
    ("1500", "Equipment", "asset", False, 90, "Fridges, ovens, furniture"),
    ("1510", "Equipment written down", "asset", False, 100, "Depreciation taken so far"),
    ("2000", "Money we owe suppliers", "liability", False, 200, "Deliveries not yet paid for"),
    ("2100", "VAT owed to ZRA", "liability", False, 210, "VAT collected inside prices"),
    ("2200", "Wages owed", "liability", False, 220, "Net pay not yet paid out"),
    ("2210", "PAYE owed", "liability", False, 230, "Deducted from pay, due to ZRA"),
    ("2220", "NAPSA owed", "liability", False, 240, "Employee and employer shares"),
    ("2230", "NHIMA owed", "liability", False, 250, "Employee and employer shares"),
    ("3000", "Owner's capital", "equity", False, 300, "What the owner has put in"),
    ("3100", "Profit kept in the business", "equity", False, 310, "Profit from earlier periods"),
    ("4000", "Food and drink sales", "income", False, 400, "Everything sold through the till"),
    ("4100", "Catering sales", "income", False, 410, "Functions and large orders"),
    ("4900", "Cash over and short", "income", False, 490, "Differences found when counting the drawer"),
    ("5000", "Cost of food sold", "expense", False, 500, "Ingredients used in what was sold"),
    ("5100", "Wasted stock", "expense", False, 510, "Thrown away or spoiled"),
    ("6000", "Wages", "expense", False, 600, "Gross pay"),
    ("6010", "NAPSA and NHIMA, employer share", "expense", False, 610, ""),
    ("6100", "Rent", "expense", False, 620, "Liberty Mall"),
    ("6110", "Electricity and water", "expense", False, 630, ""),
    ("6120", "Gas", "expense", False, 640, ""),
    ("6200", "Packaging", "expense", False, 650, "Takeaway boxes, cups, bags"),
    ("6300", "Cleaning and consumables", "expense", False, 660, ""),
    ("6400", "Repairs", "expense", False, 670, ""),
    ("6500", "Marketing", "expense", False, 680, ""),
    ("6600", "Bank and mobile money charges", "expense", False, 690, ""),
    ("6700", "Licences and fees", "expense", False, 700, ""),
    ("6800", "Depreciation", "expense", False, 710, ""),
    ("6900", "Other costs", "expense", False, 720, ""),
]

# Which account a payment method lands in.
METHOD_ACCOUNTS = {
    "cash": "1000",
    "airtel": "1020",
    "mtn": "1030",
    "zamtel": "1040",
    "card": "1050",
    "account": "1100",
}


def ensure_chart(db: Session) -> int:
    """Creates any account in the chart that is missing. Safe to run again."""
    existing = {a.code for a in db.scalars(select(Account)).all()}
    made = 0
    for code, name, kind, is_cash, sort, description in CHART:
        if code in existing:
            continue
        db.add(Account(
            code=code, name=name, type=kind, is_cash=is_cash, sort=sort,
            description=description, is_system=True, created_by="Setup",
        ))
        made += 1
    return made


def account_by_code(db: Session, code: str) -> Account | None:
    return db.scalar(select(Account).where(Account.code == code))


def _next_number(db: Session, when: date) -> str:
    return numbered(db, f"JE-{when:%Y%m}-", width=4)


class Unbalanced(ValueError):
    """Raised when an entry's debits and credits do not match."""


def post(
    db: Session,
    lines: list[tuple[str, int, int, str]],
    memo: str,
    source: str = "manual",
    reference: str = "",
    when: date | None = None,
    who: str | None = None,
    status: str = "posted",
) -> JournalEntry:
    """Writes one journal entry.

    `lines` are (account code, debit, credit, memo). Lines of zero on both
    sides are dropped, which keeps the callers below simple: they can offer a
    line for VAT or a discount without checking whether it is nil.
    """
    cleaned: list[tuple[Account, int, int, str]] = []
    for code, debit, credit, line_memo in lines:
        if debit == 0 and credit == 0:
            continue
        if debit < 0 or credit < 0:
            raise Unbalanced("A journal line cannot be negative; put it on the other side instead.")
        if debit and credit:
            raise Unbalanced("A journal line is either a debit or a credit, not both.")
        account = account_by_code(db, code)
        if not account:
            raise Unbalanced(f"There is no account {code} in the chart.")
        cleaned.append((account, debit, credit, line_memo))

    if not cleaned:
        raise Unbalanced("An entry needs at least one line.")
    debits = sum(d for _, d, _, _ in cleaned)
    credits = sum(c for _, _, c, _ in cleaned)
    if debits != credits:
        raise Unbalanced(
            f"Debits and credits must match: {debits} against {credits} ngwee."
        )

    entry_date = when or datetime.now(timezone.utc).date()
    entry = JournalEntry(
        number=_next_number(db, entry_date), entry_date=entry_date, memo=memo,
        source=source, reference=reference, status=status, created_by=who,
        posted_at=datetime.now(timezone.utc) if status == "posted" else None,
        posted_by=who if status == "posted" else None,
    )
    db.add(entry)
    db.flush()
    for position, (account, debit, credit, line_memo) in enumerate(cleaned, start=1):
        db.add(JournalLine(
            entry_id=entry.id, account_id=account.id, position=position,
            debit_ngwee=debit, credit_ngwee=credit, memo=line_memo,
        ))
    return entry


def already_posted(db: Session, source: str, reference: str) -> bool:
    """Stops the same document being posted twice."""
    return bool(db.scalar(
        select(JournalEntry).where(
            JournalEntry.source == source,
            JournalEntry.reference == reference,
            JournalEntry.reverses_id.is_(None),
        )
    ))


# ---------------------------------------------------------------------------
# what the rest of the system posts
# ---------------------------------------------------------------------------

def post_sale(db: Session, order) -> JournalEntry | None:
    """A paid order: money in, sales and VAT out.

    One line per payment method actually used, so the cash account only ever
    holds cash and the mobile money accounts can be matched against the
    operators' own statements.
    """
    if already_posted(db, "sale", order.number):
        return None
    net = order.total_ngwee - order.vat_ngwee
    lines: list[tuple[str, int, int, str]] = []
    for payment in order.payments:
        if payment.is_refund:
            continue
        code = METHOD_ACCOUNTS.get(payment.method)
        if not code:
            continue
        lines.append((code, payment.amount_ngwee, 0, payment.label if hasattr(payment, "label") else payment.method))
    lines.append(("4000", 0, net, "Food and drink"))
    lines.append(("2100", 0, order.vat_ngwee, "VAT inside the price"))
    return post(
        db, lines, f"Order {order.number}", source="sale", reference=order.number,
        who=order.created_by,
    )


def post_cost_of_sales(db: Session, order, value_ngwee: int) -> JournalEntry | None:
    """What the food on that order cost, moved from stock to cost of sales."""
    if value_ngwee <= 0 or already_posted(db, "stock", order.number):
        return None
    return post(
        db,
        [("5000", value_ngwee, 0, "Ingredients used"), ("1200", 0, value_ngwee, "Out of the store room")],
        f"Ingredients for order {order.number}", source="stock", reference=order.number,
        who=order.created_by,
    )


def post_refund(db: Session, order, payment) -> JournalEntry | None:
    """Money given back: sales and VAT reduced, money out of the same account."""
    reference = f"{order.number}-R{payment.id[:6]}"
    if already_posted(db, "refund", reference):
        return None
    share = payment.amount_ngwee / order.total_ngwee if order.total_ngwee else 0
    vat = round(order.vat_ngwee * share)
    net = payment.amount_ngwee - vat
    code = METHOD_ACCOUNTS.get(payment.method, "1000")
    return post(
        db,
        [
            ("4000", net, 0, "Refunded"),
            ("2100", vat, 0, "VAT on the refund"),
            (code, 0, payment.amount_ngwee, "Paid back"),
        ],
        f"Refund on {order.number}", source="refund", reference=reference,
        who=payment.created_by,
    )


def post_purchase(db: Session, purchase) -> JournalEntry | None:
    """A delivery checked in: stock up, money owed to the supplier up."""
    if already_posted(db, "purchase", purchase.number):
        return None
    return post(
        db,
        [
            ("1200", purchase.total_ngwee, 0, "Into the store room"),
            ("2000", 0, purchase.total_ngwee, purchase.supplier.name),
        ],
        f"Delivery {purchase.number}", source="purchase", reference=purchase.number,
        who=purchase.received_by,
    )


def post_waste(db: Session, ingredient_name: str, value_ngwee: int, reference: str, who: str | None) -> JournalEntry | None:
    """Stock thrown away: out of stock, into the waste expense."""
    value = abs(value_ngwee)
    if value <= 0:
        return None
    return post(
        db,
        [("5100", value, 0, ingredient_name), ("1200", 0, value, "Out of the store room")],
        f"Wasted {ingredient_name}", source="stock", reference=reference, who=who,
    )


def post_shift_variance(db: Session, shift) -> JournalEntry | None:
    """A drawer that counted over or short, against its own account."""
    difference = shift.variance_ngwee or 0
    if difference == 0 or already_posted(db, "shift", shift.id):
        return None
    if difference > 0:
        lines = [("1000", difference, 0, "Found in the drawer"), ("4900", 0, difference, "Over")]
    else:
        lines = [("4900", -difference, 0, "Short"), ("1000", 0, -difference, "Missing from the drawer")]
    return post(
        db, lines, f"Till counted by {shift.closed_by}", source="shift",
        reference=shift.id, who=shift.closed_by,
    )
