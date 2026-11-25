# Emergency recovery

For when the system itself cannot be reached, so the IT workspace cannot help.

## The restaurant PC (today's set-up)

| Problem | What to do |
|---|---|
| Screens show "refused to connect" | On the server PC: `.\scripts\status.ps1`. It says whether the server is running, whether the database answers, and the last lines of the log. Then `.\scripts\update.ps1` restarts it |
| "The system cannot reach its database" | `.\scripts\status.ps1`. If the password is the problem: `.\scripts\fix-database.ps1` |
| An owner is locked out, or has lost the phone for two-step sign-in | `.\scripts\reset-owner.ps1` on the server PC |
| The database is damaged or data was lost | `.\scripts\restore.ps1` with the newest backup. It restores into a test database and compares row counts before anything replaces the live one |
| The PC is stolen or dead | Install on another PC (`setup.ps1`), then restore the newest backup copied off the old PC |
| Sell while it is fixed | Paper tickets and cash. Enter them when the system is back |

## Online (once on Vercel and Render, stage 29)

| Problem | Where |
|---|---|
| Screens down | Vercel dashboard → Deployments → promote the last good one |
| Server down | Render dashboard → the service → Logs, then Manual Deploy or Rollback |
| Database down | Render dashboard → the database → Recovery |
| Nobody can sign in | Render shell: `python -m app.reset_owner owner@...` |

Keep the Render, Vercel and GitHub logins in the owners' hands, with two-step
sign-in on each. Suspending someone in the system does not take away their
access to those consoles. Remove them there too.
