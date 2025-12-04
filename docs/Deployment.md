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

1. Submit PR to `main` branch
2. GitHub Actions runs CI checks (lint, typecheck, tests etc)
3. You merge PR
4. Merge triggers Railway deployment
5. Railway builds each service using Railpack (`railpack.web.json`, `railpack.worker.json`) and deploys
6. Follow along in the Railway dashboard to see logs
7. Deploy completes in ~2-5 minutes
8. New version is live

**Live system:** https://the-flip-production.up.railway.app/

## Platform: Railway

[Railway](https://railway.app/) is the hosting platform. See [Architecture.md](Architecture.md) for system components.

---

**For operations (monitoring, rollback, backups), see [Operations.md](Operations.md)**
