# Hosting Requirements

This document describes the hosting and devops requirements of this project, alternatives considered, and the final decision of a hosting provider.

## Project Description

This project is a small internal web application for maintaining the pinball machines at a pinball museum.  It's used by the volunteer staff to log maintenance issues, upload photos and videos of problems, and track work over time.  The application is a Django-based system maintained by museum volunteers.

## Requirements

### Extremely Low Operational Burden

This project is maintained by museum volunteers:
 - **Volunteers may come and go**: there may potentially be zero knowledge hand-off from previous volunteers.  
 - **Volunteers may not be not be super technical**: they may have zero experience with devops, Django.
 - **There may be NO volunteers at times**: the museum may have no IT-proficient volunteers at times, so there can't be any ongoing tasks to keep the system running, like patching the operating system or renewing SSL certs.

So it's vital that deploying, running and maintaining the system is obvious, dead simple and has as close to zero ongoing maintenance tasks as possible.

#### Zero Ongoing Maintenance
Volunteers must not need to manage:
- OS patching  
- SSL/TLS certificate renewal  
- Server restarts  
- Container orchestration  
- Cloud resource sprawl  
- Kubernetes, Docker Swarm, CloudFormation, Terraform, etc.

#### Simple Hosting Platform
This means favoring platforms with:
- **Simple deployment model**: ideal would be checking into a GitHub branch auto-deploys the project
- **Simple logs**
- **Strong documentation and community footprint**
- **Simple UI**: geared towards hobbyists or programmers, not professional devops  
- **Single platform**: a single hosting platform must provide all the services we need; we're not going to, say, use one service for Django hosting and AWS S3 for hosting photos and videos.

#### Paas not VPS
All of the above means the hosting platform must provide a PaaS experience, not a VPS.

### Modest, Predictable Cost

We're willing to pay around $20/month.  In order to not deal with maintenance, we'd rather pay a few more bucks per month for a service that provides well more resources -- db, file storage, CPU -- than we'll need for many years.

### Managed PostgreSQL
We will use SQLite for developer localhost development (for development simplicity) and PostgreSQL for production and staging/UAT environments (for improved resilience to corruption, better disaster recovery).

The size of the database will be negligible.  The only part of the db that grows is the logs:
 - ~30 log entries per day @ 3.5kB each
 - Over 3 years ≈ ~19MB

The database must be provided by the same platform that hosts the Django app.  Ideally without it being a separate add-on, with the additional billing complexity that entails.

For the production PostgreSQL, we need:
- Automated backups  
- Easy restore  
- Simple configuration  
- No direct DBA work required  


### Managed File Storage

Museum staff will be uploading photos and videos to document issues and work done.

We project that the app needs to store:
- ~30 photos per week
- ~2 short videos per week
- We will scale down the photos and videos for storage to 2400px.  This will still let maintainers pick out small details from a photo of the entire playing surface of a pinball machine.
- Totaling ~40 GiB total across 3 years

We intend to use Django / Python's built-in resizing and thumbnail generation capabilities for photos and videos.  The hosting platform needs to support that.

The file storage must be provided by the same platform that hosts the Django app.  Ideally without it being a separate add-on, with the additional billing complexity that entails.

For this file/media storage, we need:
- Automated backups
- Easy restore
- Simple configuration: no S3 bucket plumbing or managing IAM policies


### Multiple Developers, No Per-Seat Charges

We want to support at minimum 3 concurrent developers.  Being able to support 5 would be great.

We want to avoid a per-seat fee for each developer.  This create unnecessary budgeting friction and would penalize collaboration.

### Simple Rollbacks

When a deployment introduces bugs or issues, we want to be able to quickly roll back to a previous working version.  We want to do this through a simple UI without requiring command-line tools or Git expertise.

### Environment Separation

We want separate staging/UAT and production environments to allow testing and demo'ing changes before they affect the live system.

**UAT Environment Requirements:**
- **Separate database from production** (data isolation)
- **Lower CPU/RAM resources acceptable** (not production load)
- **Can sleep when dormant** (will be idle 99% of the time).  Wake-up latency acceptable for testing/demo purposes
- **No automated backups required** (UAT data is expendable/reproducible)
- **Manual redeploy acceptable** (occasional manual intervention is acceptable for UAT)

**Production Environment Requirements:**
- **Always-on (no sleep/cold-start delays)**: because users willl access infrequently (every few hours) with sessions >20 minutes, we don't want the system to auto-sleep.  We want the first-load UX to be instant - cannot show "Application failed to respond" errors or require page refreshes.

### Custom Domain Support

We'd like to host the app at a custom domain (e.g., **maintenance**.theflip.museum).

### Low Concurrency, Low Load

This is an internal application; at most it might be used by three pinball machine maintiners at any given time.  We do not need an infinitely scalable system.

Let's keep things as simple and cheap as possible, meaning:
 - Single Django app instance per environment
 - Single database instance per environment

### Low Latency

Low latency WOULD be nice; who doesn't appreciate a fast system?  
 - **Chicago-friendly Region**: Most users will be in Chicago, if there's an option to specify a nearby hosting region.  Considering penalizing non-US hosting providers for this reason.
 - **Dedicated CPU**: a dedicated CPU would be nice, rather than a shared one.


## Evaluation of Options

### Rejected

- **Heroku**: too expensive.
- **AWS App Runner / Google Cloud Run**: too much cloud complexity (IAM, S3/GCS, VPC, container build pipelines).
- **DigitalOcean Droplets**: requires OS patching and TLS management
- **DigitalOcean App Platform**: closer to viable, but still requires separate managed Postgres + object storage (Spaces)
- **Fully serverless architectures**: would introduce too much architectural complexity.
- **Fly.io**: CLI-centric workflow with no web dashboard; requires Docker/container expertise; steeper learning curve; too DevOps-focused for volunteers.
- **Vercel / Netlify**: optimized for frontend and serverless/edge functions, not traditional Django web apps.
- **Platform.sh**: enterprise-focused; too expensive and complex for this small project.
- **Dokku / CapRover**: self-hosted PaaS requiring VPS management and OS patching.
- **Coolify**: self-hosted platform requiring VPS management and manual OS patching
- **Koyeb**: persistent file storage in public preview only.
- **Northflank**: expensive (~$43-55/mo) and probably more enterprise-focused than we need.

### Shortlist

|  | **[Railway](https://railway.app/)** | **[Miget](https://miget.com/)** | **[Render](https://render.com/)** |
| --- | --- | --- | --- |
| Plan | Pro | Hobby | Starter services + Pro workspace seats |
| [Monthly Cost](#modest-predictable-cost) | ~$22-25 ([details below](#costs)) | $5 now, $13 in 1-2 years ([details below](#costs)) | ❌ ~$64/mo for 2 devs ([details below](#costs)) |
| [# Developers For Free](#multiple-developers-no-per-seat-charges) | Unlimited | 5 included | None (every seat billed) |
| [Additional Per-Seat Cost](#multiple-developers-no-per-seat-charges) | $0 | $0 for first 5; unspecified beyond | ❗$19/dev/mo |
| [GitHub auto-deploys](#simple-hosting-platform) | ✅ | ❌ Does not yet support GitHub - showstopper  | ✅  | 
| [Automatic Upgrades (certs, OS, etc)](#zero-ongoing-maintenance) | ✅  | ✅ | ✅ |
| [Fully Managed PaaS](#paas-not-vps) | ✅ | ✅ | ✅ |
| [DB - Supports Postgres](#managed-postgresql) | ✅ | ✅ | ✅ |
| [DB - Automated Backups](#managed-postgresql) | ❌ Not native. Templates available. Manual pg_dump required.  Have to attach S3 or similar. | ✅ Automated daily backups (7-day retention) | ✅ Automated backups |
| [DB - Simple Restore](#managed-postgresql) | ❌ CLI-based pg_restore | ? | ✅ UI-based Point-in-Time Recovery |
| [ Files - Automated Backups](#managed-file-storage) | ✅ Daily | ✅ Daily | ✅ Daily snapshots |
| [ Files - Simple Restore](#managed-file-storage) | ✅ Simple GUI: Select backup by date → Restore → Deploy. Takes seconds to minutes. | ? | ✅ UI-based snapshot restore |
| [Rollback Simplicity](#simple-rollbacks) | ✅ UI-based code rollback; DB not rolled back. | ⚠️ Kubernetes-based (kubectl rollout). UI unknown. DB not rolled back. | ✅ UI-based code rollback; DB not rolled back.  |
| [Environment Separation](#environment-separation) | ✅ Persistent (dev/staging/prod) + PR environments | ✅ Multiple apps on one plan | ✅ Projects/Environments + PR previews |
| [Custom Domain Support](#custom-domain-support) | ✅ Automatic SSL via Let's Encrypt | ⚠️ Manual  cert upload/rotation | ✅ Automatic SSL via Let's Encrypt |
| [Ops UX (logs, simple UI)](#simple-hosting-platform) | Simple UI; good logs | Very simple model; limited advanced tooling | Simple UI; good logs |
| [Official Documentation](#simple-hosting-platform) | Strong | Limited | Strong |
| [Community Docs & Examples](#simple-hosting-platform) | Large community footprint | Minimal public examples | Good community footprint |
| [CPU](#low-latency) | Shared CPU | Shared CPU | Shared CPU |
| [Regions](#low-latency) | US-East (New Jersey) | us-east-1 | Ohio |
| Long Term Viability | Mature, well-funded | Younger/smaller; unclear runway | Established PaaS |
| Customer Satisfaction | Widely praised; very strong developer experience | Minimal public review footprint | Strong reputation; good developer experience |
| Overall Complexity | Slightly higher complexity (services + volumes + environment variables) | Very simple conceptual model: one plan, many apps | Moderate: projects/environments model + separate billing |

### 💰 Costs

#### Railway

**Production Environment (Always-On, No Sleep):**
- Django web service: ~$5-8/month (shared CPU, 512MB RAM, 24/7)
- PostgreSQL database: ~$3-5/month (minimal usage)
- 40GB volume storage: ~$6/month ($0.15/GB)
- **Subtotal: ~$14-19/month**

**UAT Environment (Sleeps When Idle):**
- Django web service: ~$1-2/month (sleeps after 10 min idle, wakes in <1 sec)
- PostgreSQL database: ~$1-2/month (lower usage)
- Storage: ~$2-3/month (less data than production)
- **Subtotal: ~$4-7/month**

**Developers:**
- 3-5 developers: $0 (unlimited seats on Metal infrastructure at 80%+ usage)

**Total Estimated Monthly Cost: ~$22-25/month**

Notes:
- $20/month minimum spend includes $20 usage credit
- Likely to go slightly over $20 due to two environments
- Production must remain always-on to avoid cold-start UX issues (502 errors, page refresh required)
- UAT can sleep to save costs (~$5-6/month savings vs always-on)

#### Miget

**Single Plan for Both Environments:**
- Start with Hobby 1: $5/month
  - 1 shared vCPU (Fair Scheduler), 512 MiB RAM, 10 GiB storage
  - Production + UAT apps on same plan
  - 5 collaborators included

- Upgrade to Hobby 3 when storage grows: $13/month
  - 1 shared vCPU (Fair Scheduler), 2 GiB RAM, 50 GiB storage
  - Supports ~40 GiB of photos/videos

**Developers:**
- 5 developers included free

**Total:** $5/month initially, $13/month in 1-2 years

Notes:
- Flat pricing, no usage overages
- Both environments run on single plan (Fair Scheduler manages resources)
- Manual TLS certificate management required for custom domains
- Automated backups (7-day retention) for both database and file storage

#### Render

**Workspace Seats:**
- 2 developers × $19/month = $38/month

**Production Environment (Always-On):**
- Django Web Service - Starter: $9/month (512MB RAM, 0.5 CPU, always-on)
- PostgreSQL - Basic 256MB: $7/month (1GB storage, automated backups/PITR)
- Persistent Disk Storage (40GB): $10/month ($0.25/GB)
- **Subtotal: $26/month**

**UAT Environment (Free Tier, Acceptable Trade-offs):**
- Django Web Service - Free: $0/month (512MB RAM, sleeps after 15 min)
- PostgreSQL - Free: $0/month (256MB RAM, 1GB storage, **expires after 30 days** - requires monthly redeploy)
- Persistent Disk Storage: $0/month (not needed - UAT data is expendable)
- **Subtotal: $0/month**

**Bandwidth:**
- Professional plan includes 500GB/month (likely sufficient)

**Total:** ~$64/month

Notes:
- **3.2x over budget** (~$20/month target)
- Per-seat pricing is the primary cost driver ($38/month for 2 devs)
- Free PostgreSQL expires after 30 days, requiring monthly UAT database redeploy
- Adding a 3rd developer would increase cost to ~$83/month (seat fees alone: $57/month)
- Storage costs 67% higher than Railway ($0.25/GB vs $0.15/GB)
- Strong backup/restore capabilities for production (PITR, automated snapshots)

