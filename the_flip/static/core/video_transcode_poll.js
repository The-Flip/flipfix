/**
 * Transcode status polling for video processing.
 *
 * Auto-initializes on DOMContentLoaded, finds elements with [data-media-poll-id]
 * and polls the server for status updates until videos are ready or failed.
 *
 * Features:
 * - Batched requests (all pending media in one API call)
 * - Exponential backoff (2s -> 4s -> 8s -> 10s cap)
 * - Max attempts with timeout message
 * - Pauses when tab is hidden
 * - Updates DOM when status changes to ready/failed
 *
 * Events:
 * - Listens for 'media:uploaded' on document to start polling after video uploads
 * - Dispatches 'media:ready' on container when video transcoding completes
 *
 * Expected DOM structure:
 *   <div class="media-grid__status"
 *        data-media-poll-id="123"
 *        data-media-poll-model="LogEntryMedia">
 *     Processing video...
 *   </div>
 */

(function () {
  'use strict';

  // Configuration
  // With exponential backoff: 2s -> 4s -> 8s -> 10s (capped)
  // Total timeout ~3 minutes: 2+4+8 + 17×10 = 184 seconds
  const INITIAL_INTERVAL_MS = 2000; // 2 seconds
  const MAX_INTERVAL_MS = 10000; // 10 seconds cap
  const MAX_ATTEMPTS = 20;
  const API_URL = '/api/transcoding/status/';

  // State
  let currentInterval = INITIAL_INTERVAL_MS;
  let attemptCount = 0;
  let timeoutId = null;
  let isPaused = false;

  /**
   * Get all elements currently polling for status.
   * @returns {NodeListOf<Element>} Elements with data-media-poll-id attribute
   */
  function getPendingMedia() {
    return document.querySelectorAll('[data-media-poll-id]');
  }

  /**
   * Build API URL for batch status request.
   * @param {NodeListOf<Element>} pendingElements - Elements to poll
   * @returns {string} The API URL with query parameters
   */
  function buildApiUrl(pendingElements) {
    const ids = [];
    const models = [];
    pendingElements.forEach((el) => {
      ids.push(el.dataset.mediaPollId);
      models.push(el.dataset.mediaPollModel);
    });
    return `${API_URL}?ids=${encodeURIComponent(ids.join(','))}&models=${encodeURIComponent(models.join(','))}`;
  }

  /**
   * Schedule next poll with exponential backoff.
   */
  function scheduleNextPoll() {
    attemptCount++;

    if (getPendingMedia().length > 0) {
      timeoutId = setTimeout(poll, currentInterval);
      currentInterval = Math.min(currentInterval * 2, MAX_INTERVAL_MS);
    }
  }

  /**
   * Handle successful API response.
   * @param {Object} data - Response data from API
   */
  function handlePollSuccess(data) {
    Object.entries(data).forEach(([id, info]) => {
      if (info.status === 'ready' || info.status === 'failed') {
        updateMediaElement(id, info);
      }
    });
    scheduleNextPoll();
  }

  /**
   * Handle poll errors with type differentiation.
   * @param {Error} err - The error that occurred
   */
  function handlePollError(err) {
    if (err instanceof TypeError) {
      // Network error (fetch failed, no connection)
      console.error('Transcode poll: Network error -', err.message);
    } else if (err instanceof SyntaxError) {
      // JSON parse error (invalid response)
      console.error('Transcode poll: Invalid response format -', err.message);
    } else {
      // Other errors
      console.error('Transcode poll error:', err);
    }
    // Continue polling on error - server may recover
    scheduleNextPoll();
  }

  /**
   * Main polling function. Fetches status for all pending media.
   */
  function poll() {
    if (isPaused || document.hidden) {
      return;
    }

    const pending = getPendingMedia();
    if (pending.length === 0) {
      return;
    }

    if (attemptCount >= MAX_ATTEMPTS) {
      showTimeoutMessage(pending);
      return;
    }

    const url = buildApiUrl(pending);
    fetch(url)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Server error: ${response.status}`);
        }
        return response.json();
      })
      .then(handlePollSuccess)
      .catch(handlePollError);
  }

  /**
   * Build HTML for video player.
   * @param {Object} info - Video info from API
   * @param {string} mediaId - Media ID for delete button
   * @param {boolean} hasDeleteBtn - Whether to include delete button
   * @returns {string} HTML string
   */
  function buildVideoPlayerHtml(info, mediaId, hasDeleteBtn) {
    const posterAttr = info.poster_url ? ` poster="${info.poster_url}"` : '';
    let html = `
      <video controls${posterAttr}>
        <source src="${info.video_url}" type="video/mp4">
        Your browser doesn't support video playback.
      </video>
    `;

    if (hasDeleteBtn) {
      html += `
        <button type="button" class="media-grid__delete" data-media-id="${mediaId}" aria-label="Delete media">&times;</button>
      `;
    }

    return html;
  }

  /**
   * Mark element as failed.
   * @param {Element} el - The status element
   * @param {string} [message] - Optional error message from API
   */
  function markAsFailed(el, message) {
    el.className = 'media-grid__status media-grid__status--error';
    el.textContent = message || 'Video processing failed.';
    el.removeAttribute('data-media-poll-id');
    el.removeAttribute('data-media-poll-model');
  }

  /**
   * Update DOM element when media status changes.
   * @param {string} id - Media ID
   * @param {Object} info - Status info from API
   */
  function updateMediaElement(id, info) {
    const el = document.querySelector(`[data-media-poll-id="${id}"]`);
    if (!el) return;

    const container = el.closest('.media-grid__item');
    if (!container) return;

    if (info.status === 'ready') {
      const deleteBtn = container.querySelector('.media-grid__delete');
      const mediaId = deleteBtn ? deleteBtn.dataset.mediaId : id;

      container.innerHTML = buildVideoPlayerHtml(info, mediaId, !!deleteBtn);

      // Dispatch event so media_grid.js can re-attach delete handler
      container.dispatchEvent(
        new CustomEvent('media:ready', {
          bubbles: true,
          detail: { mediaId: mediaId, container: container },
        })
      );
    } else if (info.status === 'failed') {
      markAsFailed(el, info.message);
    }
  }

  /**
   * Show timeout message on elements that exceeded max poll attempts.
   * @param {NodeListOf<Element>} elements - Elements to update
   */
  function showTimeoutMessage(elements) {
    elements.forEach((el) => {
      el.textContent = 'Taking longer than expected. Try refreshing.';
      el.removeAttribute('data-media-poll-id');
      el.removeAttribute('data-media-poll-model');
    });
  }

  /**
   * Start or restart polling.
   * Called when new videos are uploaded via media:uploaded event.
   */
  function startPolling() {
    currentInterval = INITIAL_INTERVAL_MS;
    attemptCount = 0;

    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    if (getPendingMedia().length > 0) {
      poll();
    }
  }

  // Listen for video upload events from media_grid.js
  document.addEventListener('media:uploaded', (e) => {
    if (e.detail && e.detail.hasVideo) {
      startPolling();
    }
  });

  // Listen for infinite scroll appending new cards (may contain pending videos)
  document.addEventListener('card:initialize', () => {
    if (getPendingMedia().length > 0) {
      startPolling();
    }
  });

  // Pause polling when tab is hidden, resume when visible
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      isPaused = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    } else {
      isPaused = false;
      if (getPendingMedia().length > 0) {
        poll();
      }
    }
  });

  // Auto-initialize on page load
  document.addEventListener('DOMContentLoaded', () => {
    if (getPendingMedia().length > 0) {
      poll();
    }
  });
})();
