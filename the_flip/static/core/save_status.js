/**
 * Save Status Module
 *
 * Displays a page-level "Saving..." / "Saved" / "Error saving" indicator
 * in the breadcrumb bar area. Used for background AJAX saves like checkbox
 * toggles and drag-and-drop reordering.
 *
 * Auto-initializes on DOMContentLoaded by finding [data-save-status].
 *
 * Event contract (dispatch on document):
 *   save:start  - an AJAX save has begun
 *   save:end    - an AJAX save finished; detail: { ok: true|false }
 *
 * Tracks multiple concurrent saves via an in-flight counter.
 * Delays showing "Saving..." by 300ms to avoid a jarring flash on
 * fast saves. If the save completes within that window, skips
 * straight to "Saved". Shows "Error saving" (persists) on failure.
 */
(function () {
  'use strict';

  const SHOW_DELAY = 300; // ms before showing "Saving..." (avoids flash on fast saves)

  let statusEl;
  let inFlightCount = 0;
  let errorOccurred = false;
  let showTimer;
  let fadeTimer;
  let cleanupTimer;

  function showSaving() {
    if (!statusEl) return;
    clearTimeout(fadeTimer);
    clearTimeout(cleanupTimer);
    statusEl.innerHTML =
      '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Saving\u2026';
    statusEl.className = 'save-status save-status--saving';
    statusEl.classList.remove('hidden');
  }

  function showResult() {
    if (!statusEl) return;
    clearTimeout(showTimer);
    clearTimeout(fadeTimer);
    clearTimeout(cleanupTimer);

    if (errorOccurred) {
      statusEl.innerHTML =
        '<i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i> Error saving';
      statusEl.className = 'save-status save-status--error';
      statusEl.classList.remove('hidden');
    } else {
      statusEl.innerHTML = '<i class="fa-solid fa-check" aria-hidden="true"></i> Saved';
      statusEl.className = 'save-status save-status--saved';
      statusEl.classList.remove('hidden');
      fadeTimer = setTimeout(() => {
        statusEl.classList.add('save-status--fade');
        cleanupTimer = setTimeout(() => {
          statusEl.classList.add('hidden');
        }, 500);
      }, 1500);
    }
  }

  document.addEventListener('save:start', () => {
    if (inFlightCount === 0) {
      errorOccurred = false;
      showTimer = setTimeout(showSaving, SHOW_DELAY);
    }
    inFlightCount++;
  });

  document.addEventListener('save:end', (e) => {
    inFlightCount = Math.max(0, inFlightCount - 1);
    if (e.detail && !e.detail.ok) {
      errorOccurred = true;
    }
    if (inFlightCount === 0) {
      showResult();
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    statusEl = document.querySelector('[data-save-status]');
  });
})();
