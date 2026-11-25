# Stage 24: the IT workspace, security centre and a payment fix

The first part of the master specification. Everything already in the system
was skipped; `MASTER-SPEC-STATUS.md` says where each of the 110 sections
stands and what needs an account or a decision from you.

## The IT administrator

A sixth kind of account, **IT administrator**, for the person who keeps the
system running. It can see system health, diagnostics, errors, security
events, incidents and tickets, run the fixed repairs and use the emergency
controls. It has **no access** to money, pay, prices, refunds or staff
records. It must use two-step sign-in, like the owners. Both owners can
suspend it from the Team page. `starter-accounts.ps1` makes
`it@greenbuffet.zm`.

## The IT workspace (Technical → IT workspace)

| Section | What it does |
|---|---|
| Health | Database (with its reply time), books in balance, kitchen live link, backups, screens, signing secret, environment. Email, Lenco and file storage say "not configured" honestly. Errors, security events, incidents, tickets and open sessions counted. **Run diagnostics** adds the database structure check and every integrity check |
| Repairs | Nine integrity checks (read only) and six repairs. Each repair shows what it would touch first, needs a reason, cannot run twice at once, and is **checked afterwards** by running the same check again. Things that cannot be done from here (restart, rollback, restore) are listed with why |
| Controls | Cash only, stop new orders, read-only mode. Each needs the IT person's password and a reason; both owners are told; payments already taken can still be matched |
| Incidents | Open, investigate, record root cause, fix and prevention; cannot be resolved without saying what fixed it |
| Tickets | Problems reported by anyone (menu → **Report a problem**). The page, version, device and last error reference are added automatically. Replies show on the reporter's profile under Problem reports |
| Errors | Every error the server could not handle, grouped and counted, with the reference number staff see. Passwords, tokens and database addresses are cleaned out |
| Security | Failed and locked sign-ins, refused access, rate limits, with review notes. "An event is not proof that anyone did wrong" |
| Audit | Technical and security actions |
| Resources | Database size and connections, largest tables, files, memory |

## Security added

- **The audit log is append-only inside PostgreSQL.** A trigger refuses any
  change or deletion, whoever asks.
- **Rate limits.** 30 sign-ins a minute per address, 20 unlock and two-step
  attempts, 1,200 requests a minute overall. They are counted per address and
  sign-in, so a restaurant behind one router is not one bucket. The existing
  5-wrong-passwords lockout stays.
- **Content Security Policy.** Only the system's own scripts can run, and the
  pages cannot be framed. It was checked on every screen, in light and dark.
- **Refused access is logged** as a security event.

## Fixed

- **Mobile money that fails after hand-over (from stage 22).** The order
  stayed "paid" although it owed money, and there was no way to take the
  money later. Now:
  - The order goes back to *Waiting for payment*.
  - A later payment clears the debt in the books, without repeating the
    kitchen ticket, stock, sale entry or stamps.
  - It cannot be cancelled away.
  - It does not stop the till from closing.
  - Repair *Show owing orders at the till again* fixes older ones.
- **Repaired journal entries are dated on the day of the sale**, so each
  month stays right.

## Run it on your system once installed

Open IT workspace → Run diagnostics. If it finds paid sales missing from the
books (as my test database had), use *Post paid sales missing from the books*.

## Tests

| Suite | Result |
|---|---|
| `tests/test_it.py` (new, 17) | IT sees health but not money or people; unchecked services never shown as fine; tickets and incidents; bad and duplicate repairs refused; repairs verified; cash-only, read-only and stop-orders; audit log cannot be edited or deleted; secrets cleaned from errors; refused access logged; failed mobile money owes again and is paid once (no second kitchen ticket, stock deduction or sale entry); reopen repair; sign-in rate limit |
| Money flows, security, profiles | 69 passed |
| Permission probes | 29 passed |
| Browser: diagnostics, repairs, controls, report a problem, ticket opens with page and device, no CSP errors | 4 / 4 |
| Screen sweep: 55 screens × phone and desktop × light and dark | 220 / 220 |

## Database changes (added only)

New tables: `feature_controls`, `incidents`, `support_tickets`, `case_notes`,
`repair_runs`, `error_records`, `security_events`. New role `it`. New
permissions `tickets.report` (everyone), `it.view`, `it.repair`,
`it.control`. A trigger on `audit_log`.
