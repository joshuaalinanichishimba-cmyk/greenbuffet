# The online demo

A copy of the system on Render with made-up staff, orders and money, for
showing clients who cannot come to the restaurant. It shares the code but
nothing else with the restaurant: its own database, its own address.

- Start-up: `deploy/demo-start.sh` (seed, menu, server, then made-up trade).
- `ENVIRONMENT=demo` is what makes it a demo. `app/demo_data.py` refuses to
  run without it, so made-up sales can never reach real books.
- Each time it wakes, it tops up trade to the current time, so "today" is
  never empty.
- Visitors can sell, cook, approve and look at everything, but cannot change
  passwords, accounts, roles, settings or delete anything (main.py,
  DEMO_BLOCKED), so it stays the same for the next visitor.
- All accounts use the password greenbuffet2026; the sign-in page fills it in.
- Free plan: it sleeps after 15 minutes unused and takes about a minute to
  wake. The free database is removed by Render after 30 days; recreate it, or
  move to a paid database plan, to keep the demo longer.
