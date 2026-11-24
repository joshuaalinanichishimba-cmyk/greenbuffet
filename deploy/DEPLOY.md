# Putting it on a server

When the restaurant outgrows the counter PC — or the first time a disk failure
is unacceptable — this moves the whole system to a server with HTTPS and a real
address. The application code does not change.

## What you need

- A small cloud server: 2 GB of memory is plenty, about US$12–25 a month at
  Hetzner, DigitalOcean or Vultr. Add a managed PostgreSQL if you would rather
  not look after the database yourself, which is the other US$10–15.
- A domain name, pointed at the server's address.
- Docker on the server.

## Setting it up

```bash
# on the server
git clone <your repository> /srv/greenbuffet     # or copy the folder across
cd /srv/greenbuffet/deploy
cp .env.example .env
nano .env                                        # domain, email, two passwords
docker compose up -d --build
```

For `JWT_SECRET` and `DB_PASSWORD`, use something long and random:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Caddy gets the HTTPS certificate by itself within a minute of starting, as long
as the domain points at the server and ports 80 and 443 are open. There is no
certificate to renew.

## First run

```bash
docker compose exec app python -m app.seed          # tables, roles, chart of accounts
docker compose exec app python -m app.seed_menu     # only if the menu is empty
```

The seed prints the owner's temporary password. Sign in and change it.

## Moving the data across from the PC

On the Windows machine:

```powershell
.\scripts\backup.ps1
```

Copy the newest file from `backups\` to the server, then:

```bash
docker compose cp greenbuffet-20261123.dump database:/tmp/restore.dump
docker compose exec database pg_restore -U greenbuffet -d greenbuffet --clean --if-exists /tmp/restore.dump
```

Copy `backend\uploads` across as well — that holds the photographs and stored
documents.

## Backups on the server

```
30 23 * * *  /srv/greenbuffet/deploy/backup.sh >> /var/log/greenbuffet-backup.log 2>&1
```

It keeps 30 days on the server. **Copy them somewhere else too** — a server
that fails takes its own backups with it, exactly like a disk.

## Day to day

| | |
| --- | --- |
| Logs | `docker compose logs -f app` |
| Restart | `docker compose restart app` |
| Update after a code change | `docker compose up -d --build app` |
| Is it healthy | `docker compose ps` — the app reports its own health |
| Shell | `docker compose exec app bash` |

## Before trading on it

- Check `ENVIRONMENT=production` is set. It hides the API documentation and
  sends the HSTS header.
- Sign in from a phone on mobile data, not the restaurant wifi, and confirm the
  padlock.
- Restore a backup into a scratch database and confirm the figures. A backup
  that has never been restored is not yet a backup.
- Decide what happens when the internet drops. On a server the till stops. If
  that is unacceptable, keep the counter PC set up as a fallback and accept the
  work of merging a day's trading afterwards.
