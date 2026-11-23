# Stage 10 report — settings, files, photographs and backups

One new table and an `uploads` folder inside `backend`.
`.\scripts\update.ps1` creates both.

## Settings

`/settings` holds the business details: name, address, phone, email, TPIN, VAT
number, VAT rate, the last line on the receipt, and a note shown to cashiers.

They are rows in the database, not code, and **the receipt now reads them**.
Changing the address no longer needs a new release.

Everyone with a reason to see them can; only `settings.edit` can change them.
A cashier gets the details read-only.

## Files

Photographs and PDFs, up to 8 MB each, stored on disk under `backend\uploads`
rather than in the database — a database full of photographs is slow to back up
and awkward to restore, and the backup script already copies the folder.

Each file records what it belongs to: a dish, a supplier, an employee, a
delivery, or the business itself. Only JPEG, PNG, WebP and PDF are accepted.

Every image also gets a small copy made at upload, and lists show that rather
than the original, so a counter on restaurant wifi is not pulling several
megabytes to draw a row of dishes.

**Files need the sign-in token**, which a plain `<img src>` cannot send, so the
front end fetches each one once and keeps it for the rest of the visit.

## Dish photographs

The Menu item editor now has a Photographs section. The first one is marked
"on the till", and **the till tiles show it** — which is what turns a wall of
names into something a new cashier can use quickly.

Photographs are added after an item is saved, since a file has to belong to
something that exists.

## Backups

"Back up now" on the Settings screen runs `pg_dump` into the `backups` folder
and lists what is there with sizes and times — the same files the scripts make,
so nothing competes.

For a nightly one, `.\scripts\schedule-backup.ps1` run once as Administrator
asks Windows to run `backup.ps1` every night at 23:30, whether or not anyone is
signed in. `-At 02:00` changes the time, `-Remove` cancels it. The existing
30-day cleanup applies.

The screen says plainly what a scheduled task cannot: **keep a copy off this
computer.** A disk that fails takes its own backups with it.

## Rules

| Rule | Result |
| --- | --- |
| A file type other than JPEG, PNG, WebP or PDF | 422 |
| A file over 8 MB | 413, with its actual size |
| An empty file | 422 |
| An unknown kind or attachment | 422 |
| An unknown setting key | 422, naming it |
| A VAT rate that is not a number, or outside 0–100 | 422 |
| An empty business name | 422 |
| A cashier changing settings or taking a backup | 403 |
| A stored path pointing outside the uploads folder | 404, never served |

## Tested

Against PostgreSQL: settings saved and read back through a receipt, a 1600×1200
photograph uploaded and its thumbnail served at 3 KB against the original's
30 KB, every refusal above, a real `pg_dump` backup, and a cashier turned away.
In the browser: settings saved, a file stored and its thumbnail shown, a backup
taken from the screen, a dish photograph added and then appearing on the till
tile. No horizontal scrolling at 390 px.

## Not in this stage

- **Restoring from the Settings screen.** Restoring is destructive and belongs
  at a command line where it cannot be a mis-click. `.\scripts\restore.ps1`
  already does it safely, into a test database by default.
- **Copying backups off the machine automatically.** Needs a cloud account or a
  network drive; a USB stick and a habit works today.
- **Photographs on a public website.** The menu data is ready for it; the site
  itself is its own piece of work.
