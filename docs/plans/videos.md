# Video Uploads Plan

This is the spec for supporting maintainers uploading videos while logging their work.

## Goals
- **Upload any format, transform to a widely understood format**: accept phone-recorded videos (MOV/HEVC/etc.) and transcode to widely playable H.264/AAC MP4.
- **Poster**: generate a poster image for UI display.
- **Responsive**: keep uploads responsive by offloading transcode to a background worker.
- **Minimize services/cost/ops**: reuse Postgres as the queue backend, no Redis.
- **Very low maintenance**: the volunteer staff does not want to do any maintenance on this system. Use Django patterns, admin visibility, automatic task cleanup.

## Approach
- Use **django-q2** with the ORM broker (tasks stored in Postgres/SQLite).
- Run a single worker process (`python manage.py qcluster`) to process transcodes.
- `ffmpeg` runs in the worker; cap video long side at 2400px and generate a poster.
- Automatically prune old task rows via django-q2 settings.
- Worker recycling after N tasks to prevent memory bloat from FFmpeg.

## Dependencies
- Add `django-q2` to `requirements.txt`.
- Ensure `ffmpeg` is installed in localhost and Railway.

## Settings

**File:** `the_flip/settings/base.py`

```python
INSTALLED_APPS += ["django_q"]

Q_CLUSTER = {
    "name": "the_flip_worker",
    "orm": "default",              # Use Django database as broker
    "workers": 1,                  # Single worker (sufficient for ~2 videos/week)
    "timeout": 600,                # 10 minutes per job (ffmpeg processing time)
    "retry": 660,                  # Must be > timeout; retry after 11 minutes
    "save_limit": 50,              # Keep last 50 successful tasks (auto-cleanup)
    "queue_limit": 50,             # Max queued tasks (backpressure)
    "recycle": 5,                  # ⭐ CRITICAL: Restart worker after 5 tasks to prevent FFmpeg memory leaks
    "bulk": 1,                     # Process 1 task at a time
    "catch_up": False,             # Don't process old scheduled tasks on restart
    "max_attempts": 1,             # Only try once (user can re-upload if needed)
}
```

## Model changes
- Extend `LogEntryMedia` (already has `transcoded_file`, `poster_file`, `transcode_status`, `duration`).
- `transcode_status` values: pending → processing → ready/failed.

## Tasks

**File:** `the_flip/apps/maintenance/tasks.py` (new file)

```python
"""Background tasks for video processing using django-q2."""
import subprocess
import json
import tempfile
import logging
import os
from django.core.files import File
from django_q.tasks import async_task

logger = logging.getLogger(__name__)


def enqueue_transcode(media_id):
    """Enqueue video transcode job. Called from views after video upload."""
    async_task(
        'the_flip.apps.maintenance.tasks.transcode_video_job',
        media_id,
        timeout=600,  # 10 minutes
    )


def transcode_video_job(media_id):
    """
    Django-Q2 job: transcode video to H.264/AAC MP4, extract poster, save metadata.
    Deletes original file on success to save storage.
    """
    from .models import LogEntryMedia  # Import here to avoid circular imports

    try:
        media = LogEntryMedia.objects.get(id=media_id)
        media.transcode_status = 'processing'
        media.save(update_fields=['transcode_status'])

        input_path = media.file.path

        # Get video duration using ffprobe
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_entries', 'format=duration', input_path
        ], capture_output=True, text=True, check=True)
        duration = int(float(json.loads(result.stdout)['format']['duration']))
        media.duration = duration
        media.save(update_fields=['duration'])

        # Transcode video to H.264/AAC MP4
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
            subprocess.run([
                'ffmpeg', '-i', input_path,
                '-vf', 'scale=min(iw\\,2400):min(ih\\,2400):force_original_aspect_ratio=decrease',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'main',
                '-crf', '23', '-preset', 'medium',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                '-y', tmp_video.name
            ], check=True)

            with open(tmp_video.name, 'rb') as f:
                media.transcoded_file.save(f'video_{media.id}.mp4', File(f), save=False)
        os.unlink(tmp_video.name)

        # Extract poster frame
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_poster:
            subprocess.run([
                'ffmpeg', '-i', input_path,
                '-vf', 'thumbnail,scale=320:-2',
                '-frames:v', '1',
                '-y', tmp_poster.name
            ], check=True)

            with open(tmp_poster.name, 'rb') as f:
                media.poster_file.save(f'poster_{media.id}.jpg', File(f), save=False)
        os.unlink(tmp_poster.name)

        # Delete original file to save storage (~50% savings)
        media.file.delete(save=False)

        media.transcode_status = 'ready'
        media.save()

        logger.info(f"Successfully transcoded video {media_id}")

    except Exception as e:
        logger.error(f"Failed to transcode video {media_id}: {e}", exc_info=True)
        try:
            media.transcode_status = 'failed'
            media.save(update_fields=['transcode_status'])
        except:
            pass  # Media may not exist
        raise
```

**Key implementation details:**
- Uses `async_task()` instead of RQ's `enqueue()`
- FFmpeg stderr captured via `capture_output=True` for debugging
- Temp files cleaned up with `os.unlink()` after saving to Django storage
- Original deleted after success (saves ~50% storage)
- Worker will recycle after 5 videos (per `Q_CLUSTER` settings)

## Upload flow
- Form/validation: allow `image/*,video/*` with size cap (200MB) and small video extension/MIME whitelist.
- On create/AJAX upload: detect video, set status to pending, enqueue transcode; photos follow existing path.
- UI: show poster/video when ready; “Processing…” while pending/processing; “failed” message otherwise.

## Worker
- Command: `python manage.py qcluster`.
- Railway: add a worker service with start command `python manage.py qcluster`.
- Local: run in a terminal alongside `runserver`.

## Management Commands

### Check FFmpeg Installation
Command: `python manage.py check_ffmpeg` — verifies ffmpeg/ffprobe are on PATH and prints versions.

### Check Worker Health
**File:** `the_flip/apps/maintenance/management/commands/check_worker.py`

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django_q.models import Success, Failure, OrmQ

class Command(BaseCommand):
    help = 'Check django-q2 worker health and queue status'

    def handle(self, *args, **options):
        # Check for recent successful tasks (last 24 hours)
        recent_success = Success.objects.filter(
            stopped__gte=timezone.now() - timedelta(hours=24)
        ).count()

        self.stdout.write(f"Recent successful tasks (24h): {recent_success}")

        # Check for recent failures
        recent_failures = Failure.objects.filter(
            stopped__gte=timezone.now() - timedelta(hours=24)
        ).count()

        if recent_failures > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠ Recent failed tasks (24h): {recent_failures}")
            )
            # Show latest failure
            latest_failure = Failure.objects.order_by('-stopped').first()
            if latest_failure:
                self.stdout.write(f"Latest failure: {latest_failure.func}")
                self.stdout.write(f"Error: {latest_failure.result}")
        else:
            self.stdout.write(self.style.SUCCESS("✓ No recent failures"))

        # Check queued tasks
        queued = OrmQ.objects.count()
        if queued > 0:
            self.stdout.write(f"Tasks in queue: {queued}")
            # Show oldest queued task age
            oldest = OrmQ.objects.order_by('lock').first()
            if oldest:
                age = (timezone.now() - oldest.lock).total_seconds()
                if age > 600:  # 10 minutes
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ Oldest queued task is {age/60:.1f} minutes old - worker may be stuck!"
                        )
                    )
                else:
                    self.stdout.write(f"Oldest queued task: {age:.0f}s old")
        else:
            self.stdout.write(self.style.SUCCESS("✓ Queue is empty"))

        # Check for stuck processing tasks (pending > 15 minutes)
        from the_flip.apps.maintenance.models import LogEntryMedia
        stuck_videos = LogEntryMedia.objects.filter(
            media_type='video',
            transcode_status__in=['pending', 'processing'],
            created__lt=timezone.now() - timedelta(minutes=15)
        ).count()

        if stuck_videos > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"✗ {stuck_videos} video(s) stuck in processing for >15 minutes"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("✓ No stuck video transcodes"))
```

**Usage:**
```bash
python manage.py check_worker
```

**Example output:**
```
Recent successful tasks (24h): 5
✓ No recent failures
✓ Queue is empty
✓ No stuck video transcodes
```

**When to run:**
- After deploying worker service
- When videos aren't processing
- In monitoring scripts (e.g., health check endpoint)
- Debugging production issues

## FFmpeg commands (reference)
- Transcode:
  ```
  ffmpeg -i "$INPUT" \
    -vf "scale=min(iw\\,2400):min(ih\\,2400):force_original_aspect_ratio=decrease" \
    -c:v libx264 -pix_fmt yuv420p -profile:v main -crf 23 -preset medium \
    -c:a aac -b:a 128k -movflags +faststart -y "$OUTPUT.mp4"
  ```
- Poster:
  ```
  ffmpeg -i "$INPUT" -vf "thumbnail,scale=320:-2" -frames:v 1 -y "$OUTPUT.jpg"
  ```

### Critical FFmpeg parameters (why they matter)
- `-vf "scale=min(iw\,2400):min(ih\,2400):force_original_aspect_ratio=decrease"`: Resize down so the long side is max 2400px; never upscale; preserves aspect ratio and keeps dimensions even for H.264.
- `-c:v libx264`: H.264 video codec (universal browser support vs HEVC/H.265).
- `-pix_fmt yuv420p`: **CRITICAL** for iOS Safari playback; without this, videos won’t play on iPhones.
- `-profile:v main`: Good compatibility balance (vs high/baseline).
- `-crf 23`: Quality setting (18–28 range; lower = better quality/bigger files).
- `-preset medium`: Encoding speed vs compression efficiency (faster/medium/slow/slower).
- `-c:a aac` / `-b:a 128k`: AAC audio at 128 kbps for broad support.
- `-movflags +faststart`: **CRITICAL** for progressive streaming; moves metadata to file start.
- Poster: `thumbnail,scale=320:-2` picks a representative frame and keeps aspect ratio with even dimensions.

## Monitoring & Debugging

### Django Admin Integration
Django-Q2 provides built-in admin views at `/admin/django_q/`:
- **Successful tasks**: View last 50 completed jobs (auto-pruned by `save_limit`)
- **Failed tasks**: See errors, retry failed jobs manually
- **Queued tasks**: Monitor pending video transcodes
- **Scheduled tasks**: (Not used for this feature)

### Task Lifecycle Visibility
1. User uploads video → `transcode_status = 'pending'`
2. Worker picks up job → `transcode_status = 'processing'`
3. FFmpeg completes → `transcode_status = 'ready'` (or `'failed'`)
4. UI shows video player with poster (or error message)

### Debugging Failed Jobs
If video processing fails:
1. Check django-q2 admin for error message
2. Check worker logs: `railway logs` or Railway dashboard
3. FFmpeg stderr is captured in exception logs
4. User can re-upload (simpler than retry mechanism)

### No Extra Infrastructure
- No Redis to monitor
- No separate RQ dashboard to install
- No additional failure points
- All monitoring through tools volunteers already use (Django admin)

## Deployment

### Railway (Active Platform)
1. **Add Worker Service** via dashboard:
   - Service name: `the-flip-worker`
   - Source: Same repo as web service
   - Root directory: (same as web)
   - Build command: `./build.sh`
   - Start command: `python manage.py qcluster`
   - Instance: Starter ($5/mo)

2. **Environment Variables**:
   - Copy all env vars from web service (DATABASE_URL, SECRET_KEY, etc.)
   - Railway auto-shares DATABASE_URL within project

3. **FFmpeg Installation**:
   - Already in `nixpacks.toml`: `aptPkgs = ["libheif1", "libheif-dev", "ffmpeg"]`
   - Shared build with web service

**Cost:** Worker service ~$5-10/mo (starter plan)

### Local Development

**Option 1: Two terminals**
```bash
# Terminal 1
python manage.py runserver

# Terminal 2
python manage.py qcluster
```

**Option 2: VS Code Compound Launch Configuration**

Create `.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Django: Web Server",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/manage.py",
      "args": ["runserver"],
      "django": true,
      "justMyCode": true,
      "env": {
        "DJANGO_SETTINGS_MODULE": "the_flip.settings.base"
      }
    },
    {
      "name": "Django: Q Worker",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/manage.py",
      "args": ["qcluster"],
      "django": true,
      "justMyCode": true,
      "env": {
        "DJANGO_SETTINGS_MODULE": "the_flip.settings.base"
      }
    }
  ],
  "compounds": [
    {
      "name": "Django: Full Stack (Web + Worker)",
      "configurations": ["Django: Web Server", "Django: Q Worker"],
      "presentation": {
        "hidden": false,
        "group": "Django",
        "order": 1
      },
      "stopAll": true
    }
  ]
}
```

**Usage:** Press F5 and select "Django: Full Stack (Web + Worker)" to run both services with debugging. Both stdout/stderr appear in debug console. Press Shift+F5 to stop both.

**Benefits:**
- Debug both services simultaneously
- Set breakpoints in worker code
- Single start/stop command
- Integrated console output

### Verification Checklist
After deploying worker:
- [ ] Worker service shows as "running" in dashboard
- [ ] `python manage.py check_ffmpeg` succeeds (both ffmpeg and ffprobe found)
- [ ] Upload test video, verify `transcode_status` changes: pending → processing → ready
- [ ] Check django-q2 admin shows successful task
- [ ] Verify transcoded video plays in browser
- [ ] Verify poster image displays
- [ ] Verify original file deleted (check storage size)
- [ ] Check worker memory usage after 5 videos (should recycle/drop)

## Test for FFmpeg in CI Pipeline

Add automated testing for FFmpeg availability in your CI pipeline to catch deployment issues early:
- Railway build changes could break FFmpeg installation
- nixpacks.toml edits might remove FFmpeg
- Dependency conflicts could prevent FFmpeg from being available
- Catch issues before deploying to production

### Implementation
Add a test case to the Django Test Suite; ensure the suite runs in the CI.  It tests that:
- FFmpeg binary is available on PATH
- FFprobe binary is available on PATH
- Both execute successfully
- Versions are reported (useful for debugging)


## Rejected Alternative: Redis + RQ

Redis + RQ was considered but not chosen for this project.

### Decision Factors

**Volume Analysis:**
- Expected: ~2 videos/week (~100 videos/year)
- Worker utilization: <0.1% (mostly idle)
- Processing time: 2-5 minutes per video
- No concurrent processing needed

**Cost Comparison:**
| Approach | Services | Monthly Cost | Annual Cost |
|----------|----------|--------------|-------------|
| **django-q2 (DB)** | Web + Worker | ~$15-20 | ~$180-240 |
| Redis + RQ | Web + Worker + Redis | ~$25-30 | ~$300-360 |
| **Savings:** | -1 service | **-$10/mo** | **-$120/year** |

**Operational Complexity:**
| Factor | django-q2 (DB) | Redis + RQ |
|--------|----------------|------------|
| Services to deploy | 2 | 3 |
| Services to monitor | 2 | 3 |
| Infrastructure knowledge | Django only | Django + Redis |
| Task visibility | Django admin ✅ | Separate dashboard |
| Volunteer handoff | Easy ✅ | Moderate |
| Failure points | 2 | 3 |

**Performance Trade-offs:**
- **Redis:** Job pickup ~10-50ms, pub/sub architecture
- **django-q2 (DB):** Job pickup ~1-5 seconds, polling architecture
- **Impact:** Negligible - videos process in background over 2-5 minutes anyway
- **Verdict:** 5-second pickup delay doesn't matter for 3.5-day average job spacing

### Why Database-Backed Queue Was Chosen

1. **Simpler Architecture**
   - 2 services instead of 3
   - One database instead of database + Redis
   - Fewer environment variables to configure
   - Single platform (Railway) vs potential multi-platform

2. **Lower Cost**
   - No Redis monthly fee ($60-120/year savings)
   - Same worker cost (unavoidable)
   - Better value for volunteer organization budget

3. **Better Volunteer Experience**
   - Tasks visible in Django admin (already familiar)
   - No Redis concepts to learn (eviction policies, memory tuning, persistence)
   - Easier debugging (all data in one database)
   - Simpler deployment (one less service to configure)

4. **Maintenance-Free**
   - Automatic task cleanup via `save_limit` setting
   - No Redis memory management needed
   - No Redis version upgrades to track
   - Database already has backup strategy

5. **Django-Native**
   - Uses ORM (volunteers already know this)
   - Admin integration out of the box
   - Same patterns as rest of codebase
   - No impedance mismatch

### When Redis Would Be Better

Redis + RQ would be the better choice if:
- ❌ Processing >100 videos/day (we process ~0.3/day)
- ❌ Need sub-second job pickup (we don't)
- ❌ Complex multi-queue workflows (we have one queue)
- ❌ High-throughput requirements (we have low volume)
- ❌ Already using Redis for caching (we're not)
- ❌ Full-time DevOps team (we have volunteers)
