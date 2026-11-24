# Stage 12 report — into service

The last stage. No new features: this is what turns a system that runs on a
laptop into one a restaurant can trade on.

## One address instead of two

The front end is now built once and served by the backend itself. Everything
lives at a single address on a single port, which means:

- staff devices need one URL, not two;
- there is no CORS at all, because nothing is cross-origin;
- refreshing on any page works, because every path that is not the API returns
  the app and lets it route in the browser.

`.\scripts\serve.ps1` builds the front end and runs it this way, listening on
the network, with no reloading. `.\scripts\run.ps1` is unchanged for
development.

## It runs on the restaurant wifi

`serve.ps1` prints both addresses when it starts:

```
  Open it at:
    http://localhost:8000
    http://192.168.1.42:8000
```

The second one works from a phone, a kitchen tablet or the manager's laptop on
the same wifi. Write it on a card by the till.

## It starts with Windows

`.\scripts\install-service.ps1`, run once as Administrator:

1. opens the port in the Windows firewall for the local network only;
2. registers a task that starts the system when the computer starts, before
   anyone signs in, and restarts it if it stops;
3. builds the front end and starts it now.

`-Remove` undoes all three. Run it again after installing a new stage, so the
front end is rebuilt.

The practical effect: someone turns the computer on in the morning and the
system is already there.

## Production mode is different from development

With `ENVIRONMENT=production` in `backend\.env`, the API documentation at
`/docs` and the machine-readable `/openapi.json` are switched off, and the HSTS
header is sent. Neither is wanted in a restaurant; both are useful to someone
probing.

## Moving to a server, when you want to

`deploy/` holds everything needed, and the application code needs no changes:

- **Dockerfile** — two stages, so the finished image carries no Node and no
  build tools, runs as a user rather than root, includes `pg_dump` so the
  backup button works, and reports its own health.
- **docker-compose.yml** — PostgreSQL 18, the application, and Caddy in front
  for HTTPS. Caddy gets the certificate itself and renews it; there is nothing
  to remember.
- **Caddyfile** — HTTPS, compression, the security headers, and a body limit
  large enough for photographs.
- **backup.sh** — the nightly backup for a server, 30 days kept.
- **DEPLOY.md** — the steps, including moving the data across from the PC with
  `backup.ps1` and `pg_restore`, and what to check before trading on it.

The compose file was validated here. **The image itself was not built**, because
this sandbox has no Docker daemon — the first `docker compose up -d --build` on
the server is also the first real build. Allow for that taking a few minutes
and for a typo to surface then.

Roughly US$12–25 a month for a small server, or US$25–40 with a managed
database.

## Written for the people who will use it

Four documents, meant to be printed:

- **FOR-THE-CASHIER** — opening the till, taking an order and a payment,
  closing and counting, and the five things that commonly go wrong.
- **FOR-THE-KITCHEN** — reading the board, the amber and red timings, the
  station buttons, and what to do when something runs out.
- **FOR-THE-MANAGER** — daily, weekly and monthly routines; what only a manager
  can do; what to watch for. The one to read first.
- **TILL-WALL-SHEET** — one page to tape beside the till.

And **TECHNICAL-HANDOVER** for whoever maintains the system: the shape of it,
the eight rules the code holds to and why, what posts to the books on its own,
every command, what to do when something is wrong, and the known limits.

## Tested

The whole system signed into and used on a single port, on a laptop and a
phone, with no sideways scrolling. Deep links and refreshes work. The 32 tests
pass. Production mode confirmed to hide the documentation. The compose file
validates.

## Where that leaves it

Twelve stages, all finished. The system takes money, feeds the kitchen, moves
stock, keeps double-entry books, runs payroll, reports on all of it, and backs
itself up nightly.

Three things are worth doing before it handles a real service:

1. **Set the real menu prices.** The till sells at whatever is in there.
2. **Count the store room once**, so stock starts from the truth rather than
   from zero.
3. **Confirm the payroll rates** with ZRA, NAPSA and NHIMA. The system flags
   them until someone ticks that box.

After that it is a question of using it, and fixing what the first fortnight
turns up — which is a different kind of work from building it.
