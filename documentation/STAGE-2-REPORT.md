# Stage 2 report — staff accounts, roles and session handling

Built on top of Stage 1. No database columns changed, so an installed copy
updates by replacing the files and running `.\scripts\update.ps1`.

## What you can now do in the app

**Staff accounts** (`/users`, needs the *user accounts* permission)

- Create an account from the browser. Leave the password to the system and it
  issues a temporary one, shown once, to hand to the member of staff. They must
  choose their own password before they can use anything.
- Reset anyone's password. A reset also clears the sign-in lockout, so a
  cashier locked out mid-shift is working again in seconds.
- Change a name, the email used to sign in, and the role, from the table.
- Disable an account when someone leaves, and enable it again if they return.
  Nothing is deleted, so their past sales and journal entries keep their author.

**Roles** (`/roles`, needs the *roles and permissions* permission)

- Tick permissions by area for any role, with All/None per area.
- Add a role of your own, for example a supervisor who may approve voids but
  not touch payroll.
- Save is disabled until something actually changed, and the screen says that
  staff pick up the change at their next sign-in.

**Activity log** (`/activity`, needs the *audit logs* permission)

- Every sign-in, account change, password reset and role change, newest first,
  filterable by area. Written once, never edited. Times shown in Lusaka time.

## Rules the server enforces (not the browser)

Each was tested against the running database, not just read in the code.

| Rule | Result |
| --- | --- |
| A cashier calling the admin endpoints | 403 with a plain-language message |
| Removing role management from owner or administrator | 409, refused |
| Removing your own administrator access | 409, refused |
| Disabling your own account | 409, refused |
| Reusing an email that already has an account | 409, refused |
| Signing in to a disabled account | 401 |
| Five failed sign-ins | 429 for 15 minutes |
| A password reset after a lockout | Lockout cleared, sign-in works |
| An unknown permission code | 422, nothing saved |

## Two details worth knowing

**Temporary passwords avoid lookalike characters.** They are drawn from an
alphabet with no `0`/`O` and no `1`/`l`/`I`, because these are read off a screen
and typed by hand, and a misread character is indistinguishable from a wrong
password. This came out of a real sign-in failure during Stage 1.

**A new account cannot inherit a lockout.** Failed sign-ins are recorded against
the email address, whether or not an account exists — that is deliberate, so
guessing addresses is slowed down too. Creating an account, or moving one to a
new address, now clears the failures for that address first; otherwise a brand
new cashier could be locked out on their first day by someone else's typing.

## Session handling

- The token lasts eight hours, which covers a shift.
- The browser remembers when it expires. A tab opened after expiry goes straight
  to the sign-in page instead of firing requests that will fail.
- Any rejected token anywhere in the app returns the user to the sign-in page
  with one message, rather than a screen of errors.
- A banner appears in the last fifteen minutes, so a sign-in does not end in the
  middle of taking money.
- Wrong password and expired session say different things.

## Tested

- API suite against PostgreSQL 16: every row in the table above.
- Browser run with Playwright: owner creates a cashier, reads the temporary
  password, resets it, edits a role, reads the activity log; the cashier is
  forced to change the password, sees only the dashboard in the navigation, and
  is turned away from `/users`.
- `vue-tsc` clean, production build clean.
- No horizontal scrolling at 390 px, the width of a phone.

## Not in this stage

Self-service "forgot password" by email needs an email account for the business
and is better placed with the rest of the notification work. Until then a reset
is done by the owner or an administrator, which for a single restaurant is
usually faster anyway.
