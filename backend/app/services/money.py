"""Turning ngwee into something a person reads.

Money is whole ngwee everywhere in this system, which is the only way to add
up thousands of sales without a fraction going missing. The moment it is shown
to a human it needs a kwacha sign and two decimal places, and that conversion
belongs in exactly one place so a receipt, a report and a text message never
disagree about what K95.00 looks like.
"""
from __future__ import annotations


def kwacha(ngwee: int | None, sign: bool = True) -> str:
    """9500 becomes 'K95.00'. Negatives keep their minus in front of the K."""
    amount = int(ngwee or 0)
    body = f"{abs(amount) / 100:,.2f}"
    prefix = "K" if sign else ""
    return f"-{prefix}{body}" if amount < 0 else f"{prefix}{body}"
