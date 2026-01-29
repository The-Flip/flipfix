# Video Reactivity

This document describes the UI feedback system for video uploads and transcoding.

## Features

- **Real-time video status**: Auto-updates UI when transcoding completes (ready/failed)
- **Upload progress feedback**: Shows "Uploading 2 of 5..." during multi-file uploads
- **Graceful timeout handling**: Stops polling after ~3 minutes, shows helpful message
- **Minimal server load**: Batched requests, pauses when tab hidden, exponential backoff

## Architecture

### Why Polling (vs WebSockets/SSE)

- Simple infrastructure (no Redis/Channels needed)
- Fits existing Django patterns
- Video uploads are infrequent (~2/week)
- Polling overhead is negligible for this volume

### Module Communication

The JavaScript modules communicate via custom events:

1. **`media:uploaded`** - Dispatched by `media_grid.js` when a video upload completes
   - Listened by `video_transcode_poll.js` to start/restart polling
   - Detail: `{ hasVideo: true }`

2. **`media:ready`** - Dispatched by `video_transcode_poll.js` when transcoding completes
   - Listened by `media_grid.js` to re-attach delete handlers
   - Bubbles up from the media container element
   - Detail: `{ mediaId, container }`

This event-based design keeps the modules decoupled - they can be included independently.

## API Endpoint

**URL:** `GET /api/transcoding/status/?ids=1,2,3&models=LogEntryMedia,LogEntryMedia,PartRequestMedia`

**Response:**

```json
{
  "1": {
    "status": "ready",
    "video_url": "/media/transcoded/video_1.mp4",
    "poster_url": "/media/posters/poster_1.jpg"
  },
  "2": {
    "status": "processing"
  },
  "3": {
    "status": "failed"
  }
}
```

**Authentication:** Requires login (uses Django's `login_required` decorator)

**Implementation:** `TranscodeStatusView` in `the_flip/apps/core/views.py`

## JavaScript Files

### video_transcode_poll.js

Polls the server for video transcoding status updates.

**Features:**

- Batch polling - Single request for all pending videos on page
- Exponential backoff - Start 2s, double each attempt, cap at 10s
- Max attempts - Stop after 60 attempts (~3 minutes at max interval)
- Visibility detection - Pause polling when tab is hidden
- Terminal state handling - Remove from poll list when ready/failed
- Timeout message - Shows "Taking longer than expected. Try refreshing."

**DOM interface:**

```html
<!-- Template adds these attributes to processing videos -->
<div class="media-grid__status" data-media-poll-id="123" data-media-poll-model="LogEntryMedia">
  Processing video...
</div>
```

### media_grid.js

Handles media upload and deletion.

**Upload progress features:**

- Shows "Uploading 1 of 5..." status during multi-file uploads
- Disables upload button during uploads (prevents double-uploads)
- Updates button text based on media state ("Upload" vs "Upload More")
- Dispatches `media:uploaded` event when videos are uploaded

## Template Integration

### Editable Media Card

`templates/core/partials/media_card_editable.html`

Include in page scripts:

```html
<script src="{% static 'core/media_grid.js' %}" defer></script>
<script src="{% static 'core/video_transcode_poll.js' %}" defer></script>
```

### Readonly Media Grid

`templates/core/partials/media_grid_readonly.html`

Only needs polling script (no upload functionality):

```html
<script src="{% static 'core/video_transcode_poll.js' %}" defer></script>
```

## Files

| File                                               | Purpose                               |
| -------------------------------------------------- | ------------------------------------- |
| `the_flip/apps/core/views.py`                      | TranscodeStatusView API endpoint      |
| `the_flip/urls.py`                                 | API route: `/api/transcoding/status/` |
| `the_flip/static/core/video_transcode_poll.js`     | Polling logic                         |
| `the_flip/static/core/media_grid.js`               | Upload/delete with progress counter   |
| `the_flip/static/core/styles.css`                  | `.media-grid__status` styles          |
| `templates/core/partials/media_card_editable.html` | Poll attributes on processing videos  |
| `templates/core/partials/media_grid_readonly.html` | Poll attributes for list views        |

## Testing

1. Upload a video, verify "Processing video..." appears
2. Wait for transcoding, verify video player appears without refresh
3. Upload 5 photos, verify "Uploading 1 of 5..." progress
4. Switch tabs during processing, verify polling pauses (check network tab)
5. Kill worker mid-transcode, verify timeout message appears after ~3 min
6. Verify failed videos show error state
