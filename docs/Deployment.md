# Deployment

## Production Environment

The live production system is deployed at: https://the-flip-production.up.railway.app/

It deploys every time the `main` branch is pushed to GitHub.

There are no other hosted environments as of yet: no staging, testing, UAT.


## Platform: Railway

[Railway](https://railway.app/) is the hosting platform.

## Deployment

 - Push `main` branch changes to GitHub
 - Railway automatically detects the push
 - Build takes ~2-5 minutes
 - You can follow along and see build logs on Railway

## Rollback

You can rollback to a previous version via the Railway dashboard.  It's point and click.

Rollbacks only affect application code, not the database.

## Application Logs

View logs in Railway dashboard

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

Access admin panel at: https://the-flip-production.up.railway.app/admin/

Monitor background tasks:
- Navigate to "Django Q" section
- View successful/failed tasks
- See queued jobs
- Manually retry failed jobs


## Database

### Backups

Railway automatically backs up the PostgreSQL database. It's a daily backup, not point in time (PITR).  Restore is point and click.


## File Storage

Railway provides persistent disk storage for uploaded photos and videos.

### File Backups & Restore

Railway automatically creates daily snapshots of the persistent disk. It's point and click.

### Storage Location

Files are stored in `/media/` directory on the persistent disk:
- Photos: `/media/log_entries/photos/`
- Videos (original): `/media/log_entries/videos/`
- Videos (transcoded): `/media/log_entries/videos/transcoded/`
- Video posters: `/media/log_entries/videos/posters/`


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

Monitor costs in Railway's dashboard.