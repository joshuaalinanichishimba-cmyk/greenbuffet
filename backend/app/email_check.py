"""Sends one test email with the settings in .env, for scripts\\email-setup.ps1.

    python -m app.email_check someone@example.com

Before sending, it goes through the mail server conversation one step at a
time (connect, encrypt, sign in) and says which step failed, because Python's
own error for most of them is just "connection closed". It never prints the
password. The real send is logged like any other email, so it also shows in
the IT workspace.
"""
import smtplib
import socket
import ssl
import sys

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import email as mail

HINTS = {
    "connect": "This computer could not reach the mail server. Check the internet connection, "
               "or a firewall blocking python.exe.",
    "greeting": "Something on this computer cut the connection before the mail server spoke. "
                "This is almost always antivirus email protection (Avast, AVG, Kaspersky, ESET, "
                "Norton, McAfee). Switch off its email or mail shield and run this again.",
    "encrypt": "The secure connection failed. Antivirus that scans encrypted traffic, or a wrong "
               "date and time on this computer, causes this.",
    "sign_in": "Google refused the sign-in: the App Password is wrong or was deleted, or 2-Step "
               "Verification is off. Make a new App Password and run the setup again.",
}


def probe() -> tuple[str, str] | None:
    """Walks the conversation with the mail server. Returns (step, error) on failure."""
    host, port = settings.SMTP_HOST, settings.SMTP_PORT
    context = ssl.create_default_context()
    step = "connect"
    try:
        raw = socket.create_connection((host, port), timeout=20)
        step = "encrypt" if port == 465 else "greeting"
        if port == 465:
            raw = context.wrap_socket(raw, server_hostname=host)
            step = "greeting"
        raw.settimeout(20)
        banner = raw.recv(512)
        if not banner.startswith(b"220"):
            return "greeting", f"unexpected reply {banner[:60]!r}" if banner else "no reply"
        raw.close()
        print(f"  Reached {host}:{port}, the server answered.")

        step = "greeting"
        smtp = smtplib.SMTP_SSL(host, port, timeout=20, context=context) if port == 465 \
            else smtplib.SMTP(host, port, timeout=20)
        with smtp:
            if port != 465:
                step = "encrypt"
                smtp.starttls(context=context)
            print("  Secure connection made.")
            step = "sign_in"
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            print("  Signed in to the mailbox.")
        return None
    except Exception as exc:  # each failure is reported with the step it happened at
        message = f"{type(exc).__name__}: {exc}"
        return step, message.replace(settings.SMTP_PASSWORD, "***") if settings.SMTP_PASSWORD else message


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Usage: python -m app.email_check someone@example.com")
        return 2
    if not mail.configured():
        print("  Email settings are incomplete in .env.")
        return 1
    if settings.EMAIL_MODE.lower() == "smtp":
        failed = probe()
        if failed:
            step, error = failed
            print(f"  Failed at: {step.replace('_', ' ')}")
            print(f"  Error: {error}")
            print(f"  {HINTS[step]}")
            return 1
    with SessionLocal() as db:
        try:
            mail.send(db, sys.argv[1], "Green Buffet test email",
                      "Email from the restaurant's system works. Sign-in codes, password reset links and "
                      "security notices will come from this address.", "test")
            db.commit()
            print("  Sent. Check the inbox (and the spam folder, the first time).")
            return 0
        except mail.EmailNotSent:
            db.commit()
            from sqlalchemy import select

            from app.models.access import EmailMessage
            last = db.scalar(select(EmailMessage).order_by(EmailMessage.at.desc()))
            print(f"  Not sent: {last.error if last else 'unknown error'}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
