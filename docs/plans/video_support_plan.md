# Video Uploads with RQ (Render & Railway)

## Goals
- Accept phone-recorded videos (MOV/HEVC/etc.) and transcode to widely playable H.264/AAC MP4.
- Generate a poster image for UI display.
- Keep uploads responsive by offloading transcode to an RQ worker.
- Deployable on Render and Railway without custom Dockerfiles.

## Requirements
- **Redis** for RQ queue.
- **RQ** Python package (worker + scheduler optional).
- **FFmpeg** available at runtime for transcode/poster extraction.
- **Storage** headroom for originals + MP4s + posters (consider pruning originals after success).

## App Changes (code-level)
- **Dependencies**: add `rq`, `rq-scheduler` (if periodic), and ensure FFmpeg is present.
- **Settings**: `RQ_REDIS_URL` (from env), job timeouts/concurrency defaults.
- **Models**: extend `LogEntryMedia` for videos: fields for `transcoded_file`, `poster_file`, `duration`, `width`, `height`, `transcode_status` (pending/processing/ready/failed), maybe `original_kept` flag.
- **Tasks**:
  - Enqueue on upload: `enqueue(transcode_video, media_id)`.
  - `transcode_video`: run FFmpeg to H.264/AAC MP4, cap long side at 2400px and constrain bitrate, extract poster (JPEG), store metadata, mark status.
  - Cleanup task to delete originals after successful transcode.
- **Validation**: server-side size limit (e.g., 200–500 MB), allowed MIME/ext for video; client hint via `accept="video/*"`.
- **UI**: render videos with `<video controls poster="...">` once ready; show “processing” status for pending/processing; surface errors if failed.

## Deploy: Render (YAML-driven)
- Add Redis service in `render.yaml`:
  ```yaml
  - type: redis
    name: the-flip-redis
  ```
- FFmpeg: add to `buildCommand` (or shared script):
  ```yaml
  buildCommand: |
    apt-get update
    apt-get install -y ffmpeg
    ./build.sh
  ```
- Worker service for RQ:
  ```yaml
  - type: worker
    name: the-flip-rq-worker
    runtime: python
    buildCommand: "<same as web>"
    startCommand: "rq worker --url $REDIS_URL default"
    envVars:
      - key: REDIS_URL
        fromService: the-flip-redis
  ```
- (Optional) Scheduler:
  ```yaml
  - type: worker
    name: the-flip-rq-scheduler
    runtime: python
    buildCommand: "<same as web>"
    startCommand: "rqscheduler --url $REDIS_URL"
    envVars:
      - key: REDIS_URL
        fromService: the-flip-redis
  ```
- Web service: keep existing, add `REDIS_URL` env from Redis service.

## Deploy: Railway (manual Redis provision)
- Provision Redis via UI/CLI (`railway add redis`); note the connection URL.
- FFmpeg: add to `nixpacks.toml`:
  ```toml
  [phases.setup]
  aptPkgs = ["libheif1", "libheif-dev", "ffmpeg"]
  ```
- Worker service (new Railway service) using same repo:
  - Build: reuse `build.sh`.
  - Start command: `rq worker --url $REDIS_URL default`.
  - Env: set `REDIS_URL` from the Redis plugin variable.
- (Optional) Scheduler service: `rqscheduler --url $REDIS_URL`.
- Web service: add `REDIS_URL` env var.

## Operational Notes
- Set RQ worker concurrency and timeouts conservatively to fit host CPU/RAM.
- FFmpeg command: transcode to H.264 main profile, AAC audio, cap resolution (long side 2400px, e.g., `-vf "scale='if(gt(iw,ih),2400,-2)':'if(gt(ih,iw),2400,-2)'"`) and bitrate; extract poster via `-vf "thumbnail,scale=..."`
  and `-frames:v 1`.
- Track job status to show UI feedback; retry failed jobs with backoff.
- Logging: capture FFmpeg stderr for debugging; consider a small management command to assert FFmpeg availability in each env.
