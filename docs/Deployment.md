# Deployment

## Production Environment

The live production system is deployed at: https://the-flip-production.up.railway.app/

There are no other hosted environments as of yet - no staging, testing, UAT.

It deploys every time the `main` branch is pushed to GitHub.


## Platform: Railway

[Railway](https://railway.app/) is the hosting platform.

## Railway Project Structure

The Railway project consists of two services:

### 1. Web Service (`the-flip`)
- **Type:** Web application
- **Runtime:** Python 3.13
- **Start command:** `gunicorn the_flip.wsgi:application`
- **Build command:** `./build.sh`
- **Resources:** Shared CPU, 512MB RAM
- **Always-on:** Yes (no sleep/cold starts)

### 2. Worker Service (`the-flip-worker`)
- **Type:** Background worker
- **Runtime:** Python 3.13
- **Start command:** `python manage.py qcluster`
- **Build command:** `./build.sh`
- **Purpose:** Processes video transcoding jobs asynchronously

Both services share the same codebase and PostgreSQL database.

## Environment Variables

Railway automatically provides `DATABASE_URL` when you attach a PostgreSQL database. Additional required environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SETTINGS_MODULE` | Django settings file | `the_flip.settings.prod` |
| `SECRET_KEY` | Django secret key | (generate with `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`) |
| `DEBUG` | Debug mode (must be False) | `False` |
| `ALLOWED_HOSTS` | Allowed hostnames | `the-flip-production.up.railway.app` |
| `ADMIN_USERNAME` | Default admin username | `admin` |
| `ADMIN_PASSWORD` | Default admin password | (secure password) |
| `DISCORD_WEBHOOK_URL` | Discord notifications webhook | (optional) |
| `EMAIL_HOST` | SMTP server | `smtp.gmail.com` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_HOST_USER` | Email username | `your-email@gmail.com` |
| `EMAIL_HOST_PASSWORD` | Email password/app password | (secure password) |
| `DEFAULT_FROM_EMAIL` | From email address | `noreply@theflip.museum` |

## Initial Deployment

### 1. Create Railway Project

1. Sign up at [railway.app](https://railway.app/)
2. Create a new project from GitHub repository
3. Select the `the_flip` repository
4. Railway will automatically detect it's a Python project

### 2. Add PostgreSQL Database

1. Click "New" → "Database" → "Add PostgreSQL"
2. Railway automatically provides `DATABASE_URL` to all services

### 3. Configure Web Service

1. Select the web service
2. Set environment variables (see table above)
3. Under "Settings" → "Deploy":
   - Build command: `./build.sh`
   - Start command: `gunicorn the_flip.wsgi:application`
4. Deploy

### 4. Add Worker Service

1. Click "New" → "Service" → "GitHub Repo"
2. Select the same `the_flip` repository
3. Set environment variables (copy from web service)
4. Under "Settings" → "Deploy":
   - Build command: `./build.sh`
   - Start command: `python manage.py qcluster`
5. Deploy

### 5. Configure Custom Domain (Optional)

1. In web service settings, go to "Settings" → "Networking"
2. Click "Generate Domain" or add custom domain
3. Update `ALLOWED_HOSTS` environment variable to include the domain
4. Railway automatically provisions SSL via Let's Encrypt

## Build Process

The `build.sh` script runs on every deployment:

1. Install Python dependencies from `requirements.txt`
2. Create media directory
3. Run test suite (`make test-ci`)
4. Run database migrations (`python manage.py migrate`)
5. Collect static files (`python manage.py collectstatic`)
6. Import sample data (maintainers, machines, maintenance records)

**Important:** Sample data is imported on every deploy, so any data added through the UI will be reset. This is intentional for the public prototype. For a real production deployment, remove the import commands from `build.sh`.

## Deployment Workflow

### Automatic Deployments

1. Push changes to the `main` branch on GitHub
2. Railway automatically detects the push
3. Both web and worker services rebuild and redeploy
4. Build takes ~2-5 minutes
5. Railway performs zero-downtime deployment

### Manual Deployments

You can manually trigger a deployment from the Railway dashboard:
1. Go to the service (web or worker)
2. Click "Deploy" → "Redeploy"

### Rollbacks

To rollback to a previous version:
1. Go to the service in Railway dashboard
2. Click "Deployments" tab
3. Find the previous working deployment
4. Click "⋮" → "Rollback to this version"

**Note:** Rollbacks only affect application code, not database migrations or data.

## Monitoring

### Application Logs

View logs in Railway dashboard:
1. Select the service (web or worker)
2. Click "Logs" tab
3. Real-time logs stream automatically

### Worker Health

Check worker status with management command:
```bash
railway run python manage.py check_worker
```

This shows:
- Recent successful tasks (last 24 hours)
- Recent failures
- Queued tasks
- Stuck video transcodes

### Django Admin

Access admin panel at: `https://your-domain.railway.app/admin/`

Monitor background tasks:
- Navigate to "Django Q" section
- View successful/failed tasks
- See queued jobs
- Manually retry failed jobs

## File Storage

Railway provides persistent disk storage for uploaded photos and videos.

### Backups

Railway automatically creates daily snapshots of the persistent disk. To restore:
1. Go to service settings
2. Click "Volumes" tab
3. Select backup snapshot
4. Click "Restore"

### Storage Location

Files are stored in `/media/` directory on the persistent disk:
- Photos: `/media/log_entries/photos/`
- Videos (original): `/media/log_entries/videos/`
- Videos (transcoded): `/media/log_entries/videos/transcoded/`
- Video posters: `/media/log_entries/videos/posters/`

## Database

### Backups

Railway automatically backs up the PostgreSQL database. Access backups:
1. Go to PostgreSQL service
2. Click "Backups" tab
3. View available backups
4. Download or restore as needed

### Manual Backup

Create manual backup via Railway CLI:
```bash
railway run pg_dump $DATABASE_URL > backup.sql
```

### Restore from Backup

```bash
railway run psql $DATABASE_URL < backup.sql
```

## FFmpeg and Dependencies

The system requires FFmpeg for video processing. This is automatically installed via `nixpacks.toml`:

```toml
[phases.setup]
aptPkgs = ["libheif1", "libheif-dev", "ffmpeg"]
```

Verify FFmpeg installation:
```bash
railway run python manage.py check_ffmpeg
```

## Troubleshooting

### Videos Not Processing

1. Check worker service is running in Railway dashboard
2. Run `railway run python manage.py check_worker`
3. Check worker logs for errors
4. Verify FFmpeg is installed: `railway run ffmpeg -version`

### 502/503 Errors

1. Check web service logs for startup errors
2. Verify environment variables are set correctly
3. Check database connection (Railway should provide `DATABASE_URL`)
4. Ensure `ALLOWED_HOSTS` includes the Railway domain

### Static Files Not Loading

1. Verify `collectstatic` ran during build (check build logs)
2. Check `STATIC_ROOT` and `STATIC_URL` in settings
3. Ensure WhiteNoise is configured in `wsgi.py`

### Database Migration Issues

If migrations fail during deployment:
1. Check migration files for conflicts
2. Manually run migrations: `railway run python manage.py migrate`
3. Check PostgreSQL service logs
4. Verify database connection string

## Cost Monitoring

Monitor Railway costs in the dashboard:
1. Click "Usage" tab
2. View current billing period usage
3. Set up usage alerts (optional)

Expected costs: ~$22-25/month for production + worker services

## Security Checklist

- [ ] `DEBUG = False` in production settings
- [ ] Strong `SECRET_KEY` generated and set
- [ ] `ALLOWED_HOSTS` configured correctly
- [ ] Admin password is strong and secure
- [ ] Email credentials use app passwords (not main password)
- [ ] Database backups enabled
- [ ] SSL/TLS enabled (automatic via Railway)
- [ ] CSRF and session cookies secure
- [ ] HSTS headers enabled (in `prod.py`)

## Railway CLI (Optional)

Install Railway CLI for advanced operations:
```bash
npm install -g @railway/cli
```

Login:
```bash
railway login
```

Common commands:
```bash
railway run <command>           # Run command in Railway environment
railway logs                     # Stream logs
railway shell                    # Open shell in Railway environment
railway status                   # Show project status
```

## Further Reading

- [Railway Documentation](https://docs.railway.app/)
- [plans/Hosting.md](plans/Hosting.md) - Hosting platform decision
- [plans/Videos.md](plans/Videos.md) - Video processing implementation
- [railway.toml](../railway.toml) - Railway configuration file
