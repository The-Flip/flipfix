# Deployment

How code gets from your local machine to production.

## Deployment Pipeline

**Local development → PR environment → Production**

1. Develop locally on a feature branch
2. Push branch and create PR → Automatic PR environment created
3. Test in PR environment
4. Merge to `main` → Automatic production deployment

## PR Environments

When you create a pull request, an ephemeral test environment is automatically created.

**Features:**
- Unique URL for each PR (e.g., `pr-123.up.railway.app`)
- Full stack deployment (database, storage, background workers)
- Automatically deleted when PR is closed
- Fresh database (no production data)

**How to access:**
- Railway posts the URL in the PR deployment checks
- Click the URL to test your changes in a live environment

**Limitations:**
- Fresh database (not a copy of production data)
- Separate from production (different domain, environment variables)

## Production Deployment

**Live system:** https://the-flip-production.up.railway.app/

**Deployment process:**
1. Merge PR to `main` branch
2. GitHub push triggers Railway
3. Railway runs `build.sh`:
   - Installs dependencies
   - Runs tests (`make test-ci`)
   - Runs migrations
   - Collects static files
4. Deployment completes (~2-5 minutes)
5. New version is live

⚠️ **Production deploys automatically on every `main` branch push**

## Platform: Railway

[Railway](https://railway.app/) is the hosting platform.

**Services:**
- Web application (Django + Gunicorn)
- PostgreSQL database
- Persistent disk storage (for media files)
- Background worker (Django Q)

**Configuration:**
- Build: `build.sh`
- Start: `gunicorn the_flip.wsgi:application`
- Runtime: Python 3.13
- System dependencies: libheif, ffmpeg (via `nixpacks.toml`)

---

**For operations (monitoring, rollback, backups), see [Operations.md](Operations.md)**