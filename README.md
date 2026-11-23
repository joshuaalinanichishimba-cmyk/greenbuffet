# The Green Buffet — management system

This branch contains the customer-ordering demo. See [Windows demo setup](documentation/CLIENT-DEMO.md).

Ordering, kitchen, inventory, accounting, HR and payroll for The Green Buffet,
Liberty Mall. Built by Altiora Technologies.

**Stage 1 of 12: the foundation.** Vue, FastAPI and PostgreSQL are connected,
with sign-in, roles and permissions working and enforced on the server. The
remaining modules are listed in `documentation/ROADMAP.md`.

This is separate from the browser demo. The demo stays online as the sales
tool; this is the real system that will run the restaurant.

## Setting it up on this computer

Open PowerShell in this folder and run the three commands below, in order.

```powershell
.\scripts\check.ps1     # what is installed, what is missing
.\scripts\setup.ps1     # installs everything and creates the database
.\scripts\run.ps1       # starts the system and opens the browser
```

`setup.ps1` asks for two passwords: one you choose for the database user
`gb_dev`, and the PostgreSQL superuser password you set when you installed
PostgreSQL. It prints the first owner sign-in at the end. You are asked to
change that password the moment you sign in.

If `check.ps1` reports missing tools, install them and then **open a new
PowerShell window** so they are on your PATH.

## Day to day

| What | Command |
| --- | --- |
| Start working | `.\scripts\run.ps1` |
| Update after a new stage | `.\scripts\update.ps1` |
| Reset a forgotten password | `cd backend` then `.\.venv\Scripts\python.exe reset_owner_password.py` |
| Load the starting menu (once) | `cd backend` then `.\.venv\Scripts\python.exe -m app.seed_menu` |
| Run the tests | `cd backend` then `.\.venv\Scripts\python.exe -m pytest tests -q` |
| Back up the database | `.\scripts\backup.ps1` |
| Back up every night | `.\scripts\schedule-backup.ps1` once, as Administrator |
| Prove a backup is good | `.\scripts\restore.ps1` |
| Stop | Close the two PowerShell windows, or Ctrl+C in each |

The backend is at <http://localhost:8000>, with interactive API documentation
at <http://localhost:8000/docs>. The front end is at <http://localhost:5173>.

## Layout

```
backend/          FastAPI, SQLAlchemy, PostgreSQL
  app/core/       settings, database, passwords, permissions
  app/models/     database tables
  app/schemas/    request and response shapes
  app/api/v1/     endpoints, kept thin
  app/services/   business rules
  app/seed.py     creates permissions, roles and the first owner
frontend/         Vue 3, TypeScript, Vite
  src/services/   API client
  src/stores/     session
  src/views/      screens
scripts/          the PowerShell commands above
documentation/    roadmap and stage reports
backups/          database dumps, never committed
```

## Rules this project follows

1. **Permissions are checked on the server, on every request.** Hiding a button
   in the front end is never the only protection.
2. **Money is written once.** A sale, its payment, its stock movements and its
   accounting entries commit together, or not at all.
3. **Financial records are never edited or deleted.** Corrections are
   reversals, so the history stays intact.
4. **Repeating a request must not charge twice.** Write endpoints take an
   idempotency key.
5. **Secrets never enter Git.** They live in `.env`, which `.gitignore`
   excludes.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `python`/`psql` not recognised | Open a new PowerShell window after installing |
| Activation blocked | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| Backend cannot find settings | Run backend commands from `backend\`, not the project root |
| Database connection refused | Check the PostgreSQL service is running in Services |
| Forgotten owner password | Delete the row in `users` and run `python -m app.seed` again |
