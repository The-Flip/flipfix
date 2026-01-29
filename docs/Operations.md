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
