# Operations

How to monitor, troubleshoot, and maintain the running application.

## Rollback

If a deployment causes issues, you can rollback to a previous version.

- Go to Railway dashboard
- Select the deployment
- Click rollback (point and click)

**To Note:**

- Rollbacks only affect application code
- Database changes (migrations) are NOT rolled back
- If a migration caused issues, you may need to create a reverse migration

## Monitoring

### Application Logs

View real-time logs in the Railway dashboard.

**Useful for:**

- Debugging errors
- Monitoring request traffic
- Checking background worker activity

### Worker Health

Check Django Q background worker status:

```bash
railway run python manage.py check_worker
```

**This shows:**

- Recent successful tasks (last 24 hours)
- Recent failures
- Queued tasks
- Stuck video transcodes

### Django Admin

Access the admin panel at: https://flipfix.theflip.museum/admin/

(Railway fallback: https://the-flip-production.up.railway.app/admin/)

**Monitor background tasks:**

1. Navigate to "Django Q" section
2. View successful/failed tasks
3. See queued jobs
4. Manually retry failed jobs

## Database

### Backups

Railway automatically backs up the PostgreSQL database daily.

**Backup type:** Daily snapshot (not point-in-time recovery)

**Restore process:**

1. Go to Railway dashboard
2. Navigate to database service
3. Select backup
4. Click restore (point and click)

### Sync production data into local dev

To develop against realistic data, refresh a local Postgres database with a
**sanitized** copy of production. This dumps prod read-only, restores into a
local container, and scrubs all PII and secrets.

**One-time setup:**

1. Install Docker.
2. Get the production Postgres **public** URL: Railway → `flip-fix` → the
   `Postgres` service → Variables → `DATABASE_PUBLIC_URL`. (The
   `*.railway.internal` host is unreachable from your machine.)
3. In `.env`, set `PROD_DATABASE_URL=<that public URL>` and uncomment the
   `DATABASE_URL` line (it points at the local Postgres from
   `docker-compose.yml`; see `.env.example`). With `DATABASE_URL` set, dev runs
   on Postgres instead of SQLite.
4. Confirm the local Postgres major version is ≥ prod's — verify prod's with
   `psql "$PROD_DATABASE_URL" -tAc 'show server_version'` and, if needed, bump
   the `image:` in `docker-compose.yml`.

**Each refresh:**

```bash
make db-up      # start the local Postgres container (first run only per boot)
make sync-prod  # dump prod (read-only) → restore locally → scrub PII
```

Then log in at <http://localhost:8000/admin/> as `admin` / `admin` (the sync
creates/refreshes this dev superuser; override with `DEV_SUPERUSER` /
`DEV_PASSWORD`).

**What the sync does and does not include:**

- **Scope:** the "maintenance core" — machines, models, locations, owners
  (contact details scrubbed), problem reports (reporter/IP/device scrubbed),
  log entries, maintenance tasks, and users/maintainers (emails faked, passwords
  made unusable). Parts, wiki, comments, and Discord links are emptied.
- **Never copied:** OAuth tokens, `constance` secrets (Discord/Anthropic keys,
  webhook URL), API keys, invitations, sessions, background-job payloads, and the
  `simple_history` audit tables — excluded at dump time so they never touch disk.
- **Media files are not synced** — image/video thumbnails will be broken links.
- **Production is only ever read** (the dump session is forced read-only).

`make db-down` stops the container (keeps data); `make db-reset` deletes it.

## File Storage

### Photo & Video Storage

Photos and videos are stored on Railway's persistent disk at `/media/`.

### File Backups

Railway automatically creates daily snapshots of the persistent disk.

**Restore process:**

1. Go to Railway dashboard
2. Navigate to volume/disk service
3. Select snapshot
4. Click restore (point and click)

## Cost Monitoring

Monitor hosting costs in Railway's dashboard.

**What to watch:**

- Monthly spend trend
- Resource usage (CPU, memory, bandwidth)
- Number of active PR environments

## Common Issues

### Video Transcoding Stuck

Check if Django Q worker is running:

```bash
railway run python manage.py check_worker
```

If worker is down, restart the service in Railway dashboard.

### Database Connection Issues

Check environment variables in Railway dashboard:

- `DATABASE_URL` should be set
- For production, ensure it's using the private connection URL

### Static Files Not Loading

Run collectstatic:

```bash
railway run python manage.py collectstatic --no-input
```

Or trigger a redeploy (Railway will run this automatically).

---

**For deployment process, see [Deployment.md](Deployment.md)**
