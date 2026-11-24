# Stage 18 report

Stage 18 is a short stage. It makes problems on the server computer easy to
see, makes the kitchen board forgiving, and finishes two things stage 17
left half done.

## 1. Seeing what the server is doing

The trouble on the server computer after stage 17 had two causes. An old copy
of the system kept running, and the real error was hidden. Both are dealt
with:

- **`run_server.py`** now starts the backend. If something is already
  listening on the port it refuses to start and says so, instead of quietly
  sharing the port. Windows allows two servers to share port 8000 when one
  listens on 0.0.0.0 and the other on 127.0.0.1, so the old copy kept
  answering. Every start, request and error goes to `logs\server.log`, which
  rotates at 1 MB and keeps five files.
- **`update.ps1`** stops anything listening on ports 8000 and 5173 before it
  starts the new version, not only Python processes from this folder. The old
  Vite window was Node, which lives in Program Files, so it slipped past the
  old check.
- **`status.ps1`** (new) reports in one go: what is listening on the port
  (and a warning if more than one thing is), whether the system answers and
  which version, whether the database answers, the scheduled task's last
  result, and the end of the log.
- **Health check:** when PostgreSQL is down, `/api/v1/health` now answers 503
  with `"database": "unreachable"` and the reason. Before, it gave a bare 500.

## 2. The kitchen board

- **Live updates actually fire now.** The live connection never told the board
  about tickets created from ordinary request handlers, and the "new order"
  message was sent before the sale was saved. Announcements now reach the
  server's event loop from worker threads, and go out only after the commit.
  A new sale appears on the board within about two seconds, tested.
- **Undo:** an eight-second bar after every tap, plus a ↶ arrow that moves a
  ticket back one step (`POST /kitchen/tickets/{id}/back`, recorded in the
  activity log).
- **Sound:** an optional two-note chime when a new ticket lands. The setting
  is stored on that screen.

## 3. Sales analytics compares periods

Each headline figure shows the change against the same number of days just
before: sales, orders, average order and cancelled orders. The comparison
was checked against the database directly.

## 4. Light or dark

The demo's colours follow the computer's light or dark setting, which is why
the till turned dark without warning on one laptop. A button in the sidebar
now cycles through *match Windows*, *always light* and *always dark*, per
device. The choice is applied before the first paint, so the screen never
flashes the wrong colours.

The brown used for notes and some tags was a fill colour from the demo and
could barely be read as text, especially in dark mode. A stronger text brown
(`--kraft-ink`) replaces it wherever brown is used for text.

## 5. Database password problems (added after installing)

On the server computer the system started but every sign-in said "Something
went wrong". The log showed PostgreSQL refusing the password for `gb_dev`.
So PostgreSQL holds a different password from the one in `backend\.env`.

- **`fix-database.ps1`** (new) checks for a `DATABASE_URL` Windows
  environment variable that would override `backend\.env` and offers to
  remove it. It then signs in exactly as the system does. If PostgreSQL
  refuses, it asks once for the `postgres` superuser password, sets `gb_dev`'s
  password to match `backend\.env`, and restarts the system.
- `backend\.env` is now found by its full path. Before, it depended on the
  folder the server was started from.
- The server log's first lines say which settings file and database it is
  using (never the password). They also warn when an environment variable
  overrides the file.
- When the database is down, screens now say "The system cannot reach its
  database" instead of "Something went wrong". The health check tells a
  refused password apart from PostgreSQL not running, and `status.ps1`
  names the right fix for each.

## 6. When nobody can sign in

**`reset-owner.ps1`** (new) sets a new temporary password for the owner, or
for any account named after it. It runs on the server computer only, since
having that computer and `backend\.env` is the proof of authority. It
switches the account back on, lifts the 15-minute lock, makes the person
choose their own password at the next sign-in, and records the reset in the
activity log.

    .\scripts\reset-owner.ps1
    .\scripts\reset-owner.ps1 chef@greenbuffet.zm

## 7. The database is checked on every start

After the password fix, the Till failed with "column categories.earns_stamp
does not exist". Every update had brought *a* database up to date. The likely
cause is an old `DATABASE_URL` Windows variable that sent the update to one
database while the server, reading `backend\.env`, used another. So the
server's database never got the stage 17 columns.

`run_server.py` now runs the same add-only check itself before it serves
anything, and logs what it added. If the stamp column is added at that point,
bowls and burritos are marked as earning stamps, just as an update would mark
them. A database that missed an update now repairs itself on the next start.

## Checks

- 32 automated tests pass; 32 of 32 permission checks pass.
- 29 of 29 screens are clean at phone and desktop width (no errors, no
  sideways scrolling).
- Kitchen: a new sale appears and chimes, Undo returns the ticket, ↶ moves it
  back a step.
- Theme: all three choices apply and survive a reload.

## Installing

    Expand-Archive green-buffet-stage18.zip -DestinationPath "D:\The Green Buffet" -Force
    cd "D:\The Green Buffet"
    .\scripts\update.ps1
    .\scripts\status.ps1

No database changes need any action: the one new endpoint uses existing
columns.
