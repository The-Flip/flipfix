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

- **Included:** a realistic copy of production — machines, owners, problem
  reports, log entries, tasks, parts, wiki, comments, and the `simple_history`
  edit history — so most dev works against real data.
- **PII scrubbed** (live rows and their history): user emails/names + passwords,
  owner contact details, and problem-report reporter/IP/device.
- **Never copied** (withheld at dump time so they never touch disk): `constance`
  secrets (Discord/Anthropic keys, webhook URL), OAuth tokens + app
  registrations, API keys, invitations, sessions, background-job payloads,
  Discord account links, and owner documents (sensitive attachments; their files
  aren't synced anyway).
- **Media files are not synced** — image/video thumbnails will be broken links.
- **Production is only ever read** (the dump session is forced read-only).

`make db-down` stops the container (keeps data); `make db-reset` deletes it.

## Email

Invitation delivery is the only thing in Flipfix that sends email. It is
configured entirely through environment variables and defaults to Django's
console backend, so with nothing set the app still works — invitations are
created and their links are shareable, and the "email" is written to the
service log.

### Variables

| Variable                                  | Notes                                                                 |
| ----------------------------------------- | --------------------------------------------------------------------- |
| `EMAIL_BACKEND`                           | Set to `django.core.mail.backends.smtp.EmailBackend` to send for real |
| `EMAIL_HOST` / `EMAIL_PORT`               | From your provider. Port 587 with TLS is the usual pairing            |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Provider credentials. Railway variables, never committed              |
| `EMAIL_USE_TLS`                           | `True` unless the provider says otherwise                             |
| `EMAIL_TIMEOUT`                           | Seconds. Bounded because sending happens inside the request cycle     |
| `DEFAULT_FROM_EMAIL`                      | Must be an address on a domain you control                            |

Only the **web** service needs these variables. Sending happens inside the
request cycle, so `worker` and `discord-bot` never send mail.

### Setting up Google Workspace SMTP relay

This is what `theflip.museum` uses. Google offers three SMTP paths and only
one of them fits:

| Host                   | Why not / why                                                                             |
| ---------------------- | ----------------------------------------------------------------------------------------- |
| `smtp-relay.gmail.com` | **Use this.** Sends as any address in the domain, to anyone.                              |
| `smtp.gmail.com`       | Rewrites `From` to the authenticating user, so invitations wouldn't come from `noreply@`. |
| `aspmx.l.google.com`   | Only delivers to your own Workspace users. Invitees have personal addresses.              |

#### 1. Enable the relay

**admin.google.com → Apps → Google Workspace → Gmail → Routing → SMTP relay
service → Add**

| Setting         | Value                            |
| --------------- | -------------------------------- |
| Name            | `Flipfix invitations`            |
| Allowed senders | **Only addresses in my domains** |
| Authentication  | Require SMTP Authentication      |
| Encryption      | Require TLS encryption           |

Authenticate rather than allowlist IPs: Railway's egress addresses are not
stable enough to allowlist. Changes usually apply within minutes, though
Google reserves up to 24 hours.

#### 2. Create the sending credential

SMTP authentication needs a real Workspace user with 2-Step Verification
enabled, then **myaccount.google.com → Security → App passwords**.

- **Make `noreply@theflip.museum` a real mailbox**, not a phantom address.
  If it doesn't exist, bounces go nowhere and nobody learns that invitations
  are failing. A licensed user or a Google Group both work.
- To avoid spending a seat, authenticate as an existing user and leave
  `DEFAULT_FROM_EMAIL` as `noreply@` — the relay's "only addresses in my
  domains" rule permits it.

If **App passwords** isn't offered, the tenant policy has disabled them.
That is the most common blocker. Either allow them for that account, or fall
back to IP allowlisting, which Railway makes impractical.

#### 3. DNS on `theflip.museum`

- **SPF** — TXT at the root: `v=spf1 include:_spf.google.com ~all`. If an
  SPF record already exists, **merge into it**. Two SPF records is a hard
  failure, not a warning.
- **DKIM** — Admin console → Apps → Google Workspace → Gmail → **Authenticate
  email**. Generate a 2048-bit key, publish the TXT at `google._domainkey`,
  then click **Start authentication**.
- **DMARC** (optional, recommended) — TXT at `_dmarc`:
  `v=DMARC1; p=none; rua=mailto:you@theflip.museum`.

**Skipping DKIM does not break sending — it sends the invitations to spam**,
which from the volunteer's side is indistinguishable from the feature being
broken.

#### 4. Railway variables (web service)

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@theflip.museum
EMAIL_HOST_PASSWORD=<16-char app password, spaces stripped>
DEFAULT_FROM_EMAIL=Flipfix <noreply@theflip.museum>
EMAIL_TIMEOUT=10
```

#### 5. Verify

Test locally first — the feedback loop is seconds instead of a redeploy. Put
the same values in `.env` and run:

```bash
python manage.py send_test_email you@example.com
```

The command prints the resolved backend and host before sending, warns if it
is still the console backend, and reports the result — so a typo in
`EMAIL_HOST` surfaces immediately.

Then set the Railway variables, redeploy, and send a real invitation to a
personal address. **Check the spam folder specifically**: that is what a
missing DKIM record looks like.

### Gotchas

- Port 587 means STARTTLS. Set `EMAIL_USE_TLS` **or** `EMAIL_USE_SSL`, never
  both — Django raises on startup if both are true.
- Google displays app passwords in four space-separated groups. Strip the
  spaces.
- A `550` on send usually means the `From` address is not in an allowed
  domain. Check the relay's allowed-senders setting before suspecting the
  password.
- Google publishes per-day relay recipient caps; read the current numbers off
  their limits page rather than trusting a figure written here. Invitation
  volume will not come close either way.

### Using a different provider

Nothing above is Google-specific in the code. Resend, SendGrid and Postmark
all speak plain SMTP, so switching is the same six variables pointed
somewhere else, plus that provider's SPF and DKIM records.

If delivery fails at invite time the maintainer is told so and shown the link
to pass on by hand, so a misconfigured provider degrades rather than blocks.
See [`Auth.md`](Auth.md) for why sending is synchronous.

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
