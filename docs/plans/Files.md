# File Storage Requirements

This documents the file/object storage requirements for video transcoding and the options considered.

## Context

This application requires file storage for uploaded photos and videos. There are two services that need to interact:

1. **Web Service**: Django web app that handles uploads and serves content to users
2. **Worker Service**: Background worker that transcodes videos using FFmpeg

The core challenge is that both services need access to the same files:

- **Web service** receives uploaded videos and must later serve the transcoded results to users
- **Worker service** needs to read original uploads and write transcoded outputs back to shared storage

### Workflow
- User uploads video via web service → saves to shared storage
- Web service enqueues transcode job (metadata stored in database)
- Worker service picks up job → reads original video from shared storage
- Worker transcodes video with FFmpeg → writes transcoded video + poster to shared storage
- Worker deletes original video → updates job status in database
- Web service serves transcoded video to users from shared storage


## Requirements

### Shared Access Between Services

The most critical requirement: **both the web service and worker service must access the same file storage**.


### Shared volumes won't work
Originally, we thought that we'd use Railway's persistent storage for this, called Volumes.  However, we discovered that Railway Volumes cannot be shared between services.

Render (another hosting provider) has a similar Persistent Disks feature, which has the same limitation.


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


### Prefer File Not Bucket Storage

There's a chance this entire system will get migrated to a machine owned by the museum, at which point we can serve the media from the project's filesystem, like we do in localhost development.   Moving to AWS S3-style buckets makes that migration harder.


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

### Reliability & Durability

**Not required:**
- Multi-AZ replication

**Why moderate standards acceptable:**
- Daily backups provide recovery path
- Content is user-generated, not business-critical
- Brief unavailability acceptable (internal app, not public-facing)
- Lost uploads can be re-uploaded by volunteers

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
