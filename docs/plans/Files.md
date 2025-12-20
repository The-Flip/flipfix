# File Storage Requirements

This documents the file/object storage requirements for video transcoding and the options considered.

## Context

This application requires file storage for uploaded photos and videos. There are two services that need to interact:

1. **Web Service**: Django web app that handles uploads and serves content to users
2. **Worker Service**: Background worker that transcodes videos using FFmpeg

The core challenge is that both services need access to the same files:

- **Web service** receives uploaded videos and must later serve the transcoded results to users
- **Worker service** needs to read original uploads and write transcoded outputs back to shared storage


## Chosen Solution: HTTP Transfer with Railway Volumes

After evaluating multiple approaches, we chose **HTTP transfer between services with separate Railway Volumes**.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Service (Django)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Railway Volume                       │  │
│  │  - Automated daily backups (6 day retention)         │  │
│  │  - Automated weekly backups (1 month retention)      │  │
│  │  - Stores: original uploads + transcoded media       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  HTTP Endpoint: POST /api/transcoding/upload/               │
│  - Receives transcoded video + poster from worker           │
│  - Token authentication (shared secret)                     │
│  - Saves to Volume                                          │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTP POST
                              │ (video + poster + metadata)
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Worker Service (Transcoding)             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │   Ephemeral Disk or Small Volume (temp files)        │  │
│  │   - No backups needed (temporary processing)         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Background Jobs:                                            │
│  1. Download original video from web service                │
│  2. Transcode with FFmpeg                                   │
│  3. POST transcoded files to web service                    │
│  4. Clean up temp files                                     │
└─────────────────────────────────────────────────────────────┘
```

### Why This Approach?

**Evaluated Options:**
1. ❌ **Railway Volumes (shared)** - Cannot be shared between services
2. ❌ **Railway Storage Buckets** - No automated backup functionality (feature request pending)
3. ✅ **HTTP Transfer with Volumes** - Chosen solution

**Key Advantages:**
- ✅ **Automated backups** via Railway Volume backups (daily + weekly schedules)
- ✅ **Filesystem-based storage** (easier future migration to museum hardware)
- ✅ **Single platform billing** (everything within Railway)
- ✅ **Simple configuration** (no AWS IAM/VPC complexity)
- ✅ **Clean separation** (web service owns all persistence)
- ✅ **UI-based restore** (Railway console for backup restoration)

**Trade-offs:**
- Network overhead for transferring transcoded files (acceptable for low volume ~3 concurrent users)
- Additional endpoint to maintain (HTTP upload handler with auth)
- Slightly more complex error handling (retry logic for failed transfers)

### Workflow

1. **Upload Phase:**
   - User uploads video via web service
   - Web service saves to its Volume
   - Web service enqueues transcode job (metadata in database)

2. **Transcoding Phase:**
   - Worker service picks up job from queue
   - Worker downloads original video from web service (via media URL or direct DB-based file access)
   - Worker transcodes video with FFmpeg to temp location
   - Worker generates poster image

3. **Transfer Phase:**
   - Worker POSTs transcoded video + poster to web service HTTP endpoint
   - Includes authentication token and metadata (log_entry_media_id)
   - Web service validates token and saves files to Volume
   - Web service deletes original uploaded video
   - Web service updates LogEntryMedia record with new file paths
   - Web service returns success response

4. **Cleanup Phase:**
   - Worker receives success confirmation
   - Worker cleans up temp files
   - Worker marks job complete in queue

5. **Serving Phase:**
   - Web service serves transcoded videos to users from Volume
   - All media access goes through Django (no direct storage access)


## File-Serving Architecture

This section documents how static files and user-uploaded media are served to browsers.

### Static Files vs Media Files

| Type | Examples | When They Change | Served By |
|------|----------|------------------|-----------|
| **Static files** | CSS, JS, app images | At deploy time | WhiteNoise |
| **Media files** | User-uploaded photos/videos | Anytime (dynamic) | Custom Django view |

### Static Files: WhiteNoise

[WhiteNoise](https://whitenoise.readthedocs.io/) serves static files collected by `collectstatic`. It's designed for files that exist at deploy time:

- Indexes all files at application startup
- Serves with efficient caching headers (ETags, Cache-Control)
- Supports gzip/brotli compression
- No runtime filesystem checks (fast)

### Media Files: Custom `serve_media` View

User-uploaded media is served by a custom Django view (`the_flip/views.py:serve_media`). This is necessary because WhiteNoise cannot serve dynamically uploaded files.

**Why not WhiteNoise for media?**

WhiteNoise explicitly warns: "WhiteNoise is not suitable for serving user-uploaded media files." The reasons:

1. **Startup-only indexing**: WhiteNoise indexes files when the app starts. Files uploaded afterward are invisible to it.

2. **Memory overhead at scale**: WhiteNoise holds a file index in memory. With thousands of user uploads (currently 6,000+ files), this adds unnecessary memory pressure and slows app startup.

3. **Wrong tool for the job**: WhiteNoise is optimized for a small, fixed set of static assets, not a growing collection of user content.

**Why not Django's `static()` helper?**

Django's `static()` URL helper (used with `DEBUG=True`) can serve media files, but:

- Only works when `DEBUG=True` (not in production)
- Redundant when we already have `serve_media`

**Why not make use of a CDN?**

A CDN caches content at edge locations, but only helps when the same asset is requested multiple times within the cache TTL. For this application:

- Infrequent access (hours between users)
- Long-tail content (each photo viewed rarely after initial upload)
- Small user base (not many concurrent requests for same asset)
- Most requests would be cache misses, still hitting origin

A CDN adds complexity without benefit for this usage pattern.

### Browser Caching Strategy

Since media filenames include UUIDs (e.g., `e5f170a9-2c7c-446a-8ab3-6e5538f1a77f-poster.jpg`), files are effectively immutable—the filename changes if the content changes. This enables aggressive browser caching:

```python
response["Cache-Control"] = "public, max-age=31536000, immutable"
```

This tells browsers to cache media for 1 year without revalidation.


### Alternatives Considered

| Option | Verdict | Reason |
|--------|---------|--------|
| **WhiteNoise for media** | ❌ Rejected | Can't serve dynamic uploads; memory overhead at scale |
| **Django `static()` helper** | ❌ Rejected | Only works in DEBUG mode; redundant |
| **CDN (CloudFront, Cloudflare)** | ❌ Rejected | Low-traffic app with infrequent access; cache misses dominate |
| **S3 + django-storages** | ❌ Rejected | Adds AWS complexity; harder to migrate to museum hardware |
| **Custom `serve_media` view** | ✅ Chosen | Simple, handles dynamic uploads, works everywhere |


## Backup Strategy

### Railway Volume Backups

The web service's Railway Volume provides comprehensive backup functionality that satisfies all requirements:

**Automated Backup Schedules:**
- **Daily Backups:** Created every 24 hours, retained for 6 days
- **Weekly Backups:** Created every 7 days, retained for 1 month

Both schedules can be enabled simultaneously on the same volume.

**Restore Process:**
1. Navigate to service's Backups tab in Railway console
2. Locate desired backup by timestamp
3. Click "Restore" button
4. Review staged changes via "Details" button
5. Deploy to complete restoration

**Pricing:**
- Incremental backups using copy-on-write technology
- Billed only for incremental changes at same rate as volume storage ($0.15/GB on Railway Metal)
- Minimal additional cost due to incremental nature

**How This Meets Requirements:**
- ✅ Daily backups (exceeds "daily minimum" requirement)
- ✅ 6+ day retention (daily) + 30 day retention (weekly) (exceeds "at least 7 days")
- ✅ Simple UI-based restore (Railway console, no CLI required)
- ✅ Automatic operation (no volunteer intervention needed)

**Configuration Steps:**
1. Create or identify Volume attached to web service
2. Navigate to Volume's settings in Railway console
3. Enable "Daily" backup schedule
4. Enable "Weekly" backup schedule
5. Verify backups are being created in Backups tab


## Implementation Details

### Authentication

**Shared Token Approach:**
- Generate secure random token (e.g., `secrets.token_urlsafe(32)`)
- Store as `TRANSCODING_UPLOAD_TOKEN` environment variable on both services
- Worker includes token in HTTP request header: `Authorization: Bearer <token>`
- Django endpoint validates token before accepting upload

**Security Considerations:**
- Token must be at least 32 bytes of randomness
- Rotate token if compromised
- Endpoint only accepts POST requests
- Validate file types (video/*, image/*)
- Limit upload size via Django's `DATA_UPLOAD_MAX_MEMORY_SIZE`

### Error Handling

**Worker Side:**
- Retry failed uploads up to 3 times with exponential backoff
- Log all upload attempts and responses
- Preserve temp files until Django confirms receipt
- If all retries fail, mark job as failed and alert

**Django Side:**
- Validate token before processing upload
- Validate log_entry_media_id exists
- Validate file types match expected formats
- Use database transaction for file save + record update
- Return detailed error messages for debugging
- Log all upload attempts (success and failure)

### Performance Considerations

**Network Transfer:**
- Transcoded videos are significantly smaller than originals (H.264 compression)
- Typical file sizes: 5-20 MB per video after transcoding
- Railway internal network should provide fast transfer speeds
- Low volume (~3 concurrent users) means network overhead is negligible

**Worker Processing:**
1. Download original video: ~5-10 seconds (depends on file size)
2. Transcode with FFmpeg: ~30-120 seconds (depends on video length)
3. Upload to Django: ~2-5 seconds (transcoded file smaller)
4. Total: ~40-135 seconds per video (acceptable for background job)


## Requirements

### Shared Access Between Services

The most critical requirement: **both the web service and worker service must access the same file storage**.

**How we solve this:** HTTP transfer allows worker to write transcoded files to web service's Volume without requiring direct shared filesystem access.


### Shared volumes won't work
Originally, we thought that we'd use Railway's persistent storage for this, called Volumes.  However, we discovered that Railway Volumes cannot be shared between services.

Render (another hosting provider) has a similar Persistent Disks feature, which has the same limitation.

**How we work around this:** Worker sends transcoded files to web service via HTTP POST, allowing web service to save to its own Volume.


### Simple Configuration

We want to avoid AWS-level complexity:

**Avoid:**
- ❌ IAM policy configuration
- ❌ VPC networking
- ❌ Terraform/CloudFormation IaC
- ❌ Separate billing/account management
- ❌ Complex access control (bucket policies, ACLs, etc.)

**Prefer:**
- ✅ Single platform billing (Railway provides everything)
- ✅ Environment variables for credentials (no IAM roles/assume role chains)
- ✅ Simple bucket creation (click or one command)
- ✅ Automatic credential injection

**How we achieve this:**
- ✅ Railway Volumes are simple to configure (attach to service, mount path, done)
- ✅ Single platform billing (everything within Railway)
- ✅ Only environment variable needed: `TRANSCODING_UPLOAD_TOKEN` (shared secret)
- ✅ No IAM, VPC, ACLs, or IaC required
- ✅ Volume creation is point-and-click in Railway console


### Prefer File Not Bucket Storage

There's a chance this entire system will get migrated to a machine owned by the museum, at which point we can serve the media from the project's filesystem, like we do in localhost development.   Moving to AWS S3-style buckets makes that migration harder.

**How we achieve this:**
- ✅ Railway Volumes provide filesystem-based storage (same as local development)
- ✅ Django uses standard `FileField` and `ImageField` (no S3-specific code)
- ✅ Files stored in standard directory structure: `media/log_entries/{id}/{uuid}-{filename}`
- ✅ Migration to museum hardware: copy Volume contents to local filesystem, update `MEDIA_ROOT`, done
- ✅ No S3 API changes needed for museum deployment


### Automated Backups

File storage must have automated backup capability:

- **Frequency:** Daily backups minimum
- **Retention:** At least 7 days
- **Restore:** Simple UI-based restore (not CLI-only)

**Why this matters:**
- Volunteer staff may accidentally delete files
- Protection against data corruption
- Need point-in-time recovery for user-uploaded content
- Backups must be automatic (volunteers won't remember to trigger manually)

**How we achieve this:**
- ✅ Railway Volume automated backups (see "Backup Strategy" section above)
- ✅ Daily schedule: 6 day retention (exceeds 7 day requirement)
- ✅ Weekly schedule: 30 day retention (bonus long-term protection)
- ✅ UI-based restore through Railway console
- ✅ Fully automatic, no volunteer intervention required


### Performance

**Required:**
- Upload speeds: ~10-50 MB/s (acceptable for volunteer workflows)
- Download speeds: ~10-50 MB/s (users view 1-2 videos per session)
- Latency: <500ms for file access (not latency-critical)

**Not required:**
- CDN/edge caching (low concurrent users, internal app)
- Multi-region replication (single US region sufficient, US East preferred)
- High IOPS (sequential video streaming, not random access)

**Context:**
- Low concurrent users (~3 max)
- Internal application (not public-facing)
- Chicago-based users (prefer US-central or US-east region)

**How we achieve this:**
- ✅ Railway Volume filesystem access is fast (local disk I/O)
- ✅ Upload/download speeds exceed requirements (volume-backed storage)
- ✅ Railway's US-East region available (closest to Chicago users)
- ✅ Network transfer between services adds ~2-5 seconds per transcode (acceptable)
- ✅ No CDN needed (Django serves media directly, low concurrent users)
- ✅ Performance far exceeds needs for ~3 concurrent users

### Reliability & Durability

**Not required:**
- Multi-AZ replication

**Why moderate standards acceptable:**
- Daily backups provide recovery path
- Content is user-generated, not business-critical
- Brief unavailability acceptable (internal app, not public-facing)
- Lost uploads can be re-uploaded by volunteers

**How we achieve this:**
- ✅ Railway's infrastructure reliability (production-grade platform)
- ✅ Daily + weekly backups provide recovery path
- ✅ Acceptable availability for internal application
- ✅ Simple restore process if needed

### Security

**Not required:**
- Public CDN URLs
- Signed URLs with expiration
- Complex IAM policies
- Encryption at rest (nice-to-have, not required)

**Why:**
- Internal application (authenticated users only)
- All access mediated through Django app
- No direct browser → storage access needed

**How we achieve this:**
- ✅ All media access goes through Django's authentication layer
- ✅ Worker → Django transfer uses token authentication
- ✅ No public URLs to storage (Django serves media)
- ✅ Railway provides network isolation between services
- ✅ Simple token-based auth sufficient for internal services


## Next Steps: Implementation Plan

When ready to implement this architecture, the following changes will be needed:

### 1. Django Web Service Changes

**New HTTP Upload Endpoint:**
- Create view: `receive_transcoded_media()` in `the_flip/apps/maintenance/views.py`
- Accept multipart/form-data with fields:
  - `video_file`: transcoded video file
  - `poster_file`: generated poster image
  - `log_entry_media_id`: ID to update
  - `Authorization` header: Bearer token
- Add URL route in `the_flip/apps/maintenance/urls.py`: `/api/transcoding/upload/`
- Validate token, save files, update LogEntryMedia record, delete original
- Return JSON response with success/error status

**Settings:**
- Add `TRANSCODING_UPLOAD_TOKEN` setting (read from env var)
- Keep existing `MEDIA_ROOT` and `MEDIA_URL` configuration

**Dependencies:**
- No new dependencies required (Django handles multipart uploads natively)

### 2. Worker Service Changes

**Modify Transcoding Task:**
- Update `transcode_video_job()` in `the_flip/apps/maintenance/tasks.py`
- After successful transcode, POST files to Django endpoint
- Use `requests` library for multipart upload:
  ```python
  files = {
      'video_file': open(transcoded_path, 'rb'),
      'poster_file': open(poster_path, 'rb'),
  }
  data = {'log_entry_media_id': media.id}
  headers = {'Authorization': f'Bearer {settings.TRANSCODING_UPLOAD_TOKEN}'}
  response = requests.post(django_url, files=files, data=data, headers=headers)
  ```
- Implement retry logic (3 attempts with exponential backoff)
- Clean up temp files only after successful upload confirmation

**Settings:**
- Add `DJANGO_WEB_SERVICE_URL` (e.g., `https://the-flip.railway.app`)
- Add `TRANSCODING_UPLOAD_TOKEN` (same value as web service)

**Dependencies:**
- Add `requests` to requirements.txt if not present (likely already installed)

### 3. Railway Configuration

**Web Service Volume:**
- Ensure Volume is attached to web service
- Mount path: `/app/media` (or wherever `MEDIA_ROOT` points)
- Enable automated backups:
  - Daily schedule (6 day retention)
  - Weekly schedule (1 month retention)

**Worker Service:**
- Option A: Use Railway's ephemeral disk for temp files (simpler, no cost)
- Option B: Attach small Volume for temp processing (more reliable, minimal cost)

**Environment Variables:**
- Generate secure token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Set `TRANSCODING_UPLOAD_TOKEN` on both services (same value)
- Set `DJANGO_WEB_SERVICE_URL` on worker service (web service's Railway URL)

### 4. Testing Strategy

**Unit Tests:**
- Test Django upload endpoint with valid token
- Test Django upload endpoint with invalid token
- Test file validation (type, size)
- Test LogEntryMedia record updates

**Integration Tests:**
- Full flow: upload → transcode → HTTP transfer → serve
- Test error scenarios: network failure, invalid files, missing records
- Test retry logic on worker side

**Manual Testing:**
- Deploy to Railway staging environment
- Upload test video through web interface
- Monitor transcoding job logs
- Verify transcoded video appears in web service
- Verify original video is deleted
- Verify backups are being created in Railway console

### 5. Migration from Current Setup

**If Already Running in Production:**
1. Deploy worker changes first (falls back to current behavior if endpoint doesn't exist)
2. Deploy web service changes (adds new endpoint)
3. Test with new uploads
4. Monitor for errors
5. Verify backups are working

**If Moving from Local to Railway:**
1. Create web service Volume in Railway
2. Enable backup schedules
3. Deploy web service with Volume attached
4. Upload media files to Volume (via Django admin or management command)
5. Deploy worker service
6. Configure environment variables
7. Test full flow

### 6. Monitoring & Maintenance

**What to Monitor:**
- Worker upload success/failure rates
- Django endpoint response times
- Storage volume usage (Railway console)
- Backup creation success (Railway console)

**Regular Maintenance:**
- Review backup retention (ensure backups are being created)
- Monitor storage growth (transcode quality settings may need adjustment)
- Rotate `TRANSCODING_UPLOAD_TOKEN` periodically (e.g., annually)

### 7. Documentation for Museum Staff

**Backup Restoration Guide:**
1. Log into Railway console
2. Navigate to web service → Volumes → Backups tab
3. Select backup by timestamp
4. Click "Restore"
5. Click "Deploy" to apply

**Troubleshooting Common Issues:**
- Video not transcoding: Check worker service logs
- Transcoded video not appearing: Check Django upload endpoint logs
- Storage full: Review storage usage, adjust transcode quality settings
