# Stage 25: email

The system can now send email: sign-in codes, password reset links, address
confirmation, a safe way to change an address, and security notices. To begin
with it sends from Joshua's Gmail through a Google App Password. When the
restaurant has its own domain, the same settings take that mailbox instead
(`scripts\email-setup.ps1` again).

Version 1.25.0.

## Setting it up (once, on the server computer)

1. On the Gmail account, switch on 2-Step Verification if it is not on.
2. Make an App Password at https://myaccount.google.com/apppasswords
   (name it "Green Buffet"). Google shows 16 letters once.
3. Run `.\scripts\email-setup.ps1` and paste those 16 letters when asked. They
   do not show as you type. They are written only to `backend\.env` on that
   computer, which the push script refuses to send to GitHub.
4. It sends a test email to the same address and says whether it went.
5. Run `.\scripts\update.ps1` so the system restarts and starts sending.

Never type the App Password into a chat, a message or a document. To stop all
email: `.\scripts\email-setup.ps1 -Off`. To cut it off from Google's side,
delete the App Password at the same address.

## What each person does

Profile → **Security** → **Email address**:

- **Confirm** the address: a six-digit code arrives, type it in. Until an
  address is confirmed, nothing that matters is sent to it (no reset links, no
  codes).
- **Change** the address: a code goes to the old address and another to the
  new one, and both are needed. Both addresses are told it happened, and every
  other device is signed out. An owner cannot change another owner's address
  at all, and a manager changing a staff member's address makes them confirm
  it again.

The owner accounts still use the starter addresses (`owner@greenbuffet.zm`).
Change them to real addresses first, from each owner's own profile.

## Two-step sign-in by email

Owners and IT must use two-step sign-in. They can now choose:

| Method | How it works |
|---|---|
| Email code | After the password, a six-digit code is emailed. It works for 5 minutes, once. A new one can be asked for after 60 seconds, at most five in 15 minutes, and asking for a new one cancels the old one. Five wrong tries and that code is dead |
| Authenticator app | As before (stage 23). Works with no internet on the phone |

Either way, the eight recovery codes still work if the email or phone is not to
hand. Anyone else can switch two-step on by email if they want it.

## Forgotten passwords

"Forgot your password?" on the sign-in screen. It always gives the same
answer whether or not the address exists, so it cannot be used to find out
who works here. If the address belongs to an account with a **confirmed**
email, a link is sent. The link works for 30 minutes, once, and using it signs
the person out everywhere. The new password must be at least 10 characters,
not a common one, and not contain their name or email.

## Security notices by email

Important notices that already went to the bell (new device, repeated wrong
passwords, password or address changed, account suspended, two-step changed)
now also go by email to confirmed addresses. Notices a person can switch off
stay in the system only.

## What is kept, and what is not

- Codes are never stored. Only a keyed fingerprint is kept, so even someone
  with the database cannot read a code.
- The email log (IT workspace → **Email**) keeps who, when, which kind, whether
  it went, and the error if not. It never keeps the message, a code or a link.
- No password is ever sent by email.
- Nobody, including IT, can see a code. There is no bypass code.

## IT workspace → Email

Shows whether email is set up (never the password), what has been sent, and
failures with the reason. **Send a test** goes only to the IT person's own
confirmed address. Failed codes are not retried on purpose: they expire in
minutes, so the person asks for a new one.

## Tests

| Suite | Result |
|---|---|
| `tests/test_email.py`: confirm an address; wrong code counted and dead after five; code expires; resend waits 60 s and is limited; a new code cancels the old; emailed sign-in code works once and only for its own sign-in; recovery code instead; forgotten password same answer for everyone; reset link works once and signs out everywhere; weak passwords refused; change needs both codes and tells both addresses; an owner's address cannot be changed by anyone else; nothing secret in the email log; test email only to your own address | 17 passed |
| `test_money_flows.py`, `test_security.py`, `test_profiles.py`, `test_it.py` | 86 passed |
| `probe_customer_security.py` | 29 passed |
| Browser: forgotten password, reset link, old password refused, emailed code sign-in with the address masked | Pass |
| Screen sweep: 57 screens × phone and desktop × light and dark | 228 / 228 clean |

Sending through Gmail itself was not tested here, because that needs the App
Password, which only you should type. `email-setup.ps1` tests it on your
computer.

## Moved

Approval thresholds, dual approval and the owner security summary, listed
under 25 before, move to stage 28 with the other owner controls.
