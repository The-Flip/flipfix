/**
 * Generic media reorder driver.
 *
 * Drives any container with the following data attributes:
 *   data-media-reorder            (marker)
 *   data-reorder-url="/profile/"  (URL of the parent view; reorder action dispatches here)
 *
 * Each draggable child must carry:
 *   data-id="<media pk>"
 *
 * The handle within each child must have class `media-reorder__handle`.
 *
 * On sort, POSTs form-encoded:
 *   action=reorder_media
 *   ordered_ids=<id1>&ordered_ids=<id2>&...
 *
 * Server returns {success: true} on success, or 400 with {error: ...} if the
 * submitted set doesn't exactly match the parent's current media. On 400 we
 * surface a "please refresh" message — the page state has diverged.
 *
 * Requires SortableJS (loaded via CDN in the parent template) and core.js
 * (for getCsrfToken / showMessage).
 */
(function () {
  'use strict';

  function initContainer(container) {
    const url = container.dataset.reorderUrl;
    if (!url) return;

    // eslint-disable-next-line no-undef
    new Sortable(container, {
      handle: '.media-reorder__handle',
      animation: 150,
      ghostClass: 'media-reorder__item--ghost',
      chosenClass: 'media-reorder__item--chosen',
      dragClass: 'media-reorder__item--drag',
      onSort: () => {
        saveOrder(container, url);
      },
    });
  }

  async function saveOrder(container, url) {
    const items = container.querySelectorAll(':scope > [data-id]');
    const formData = new FormData();
    formData.append('action', 'reorder_media');
    formData.append('csrfmiddlewaretoken', getCsrfToken());
    items.forEach((item) => {
      formData.append('ordered_ids', item.dataset.id);
    });

    document.dispatchEvent(new CustomEvent('save:start'));

    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!response.ok) {
        reportFailure();
        return;
      }
      document.dispatchEvent(new CustomEvent('save:end', { detail: { ok: true } }));
    } catch {
      reportFailure();
    }
  }

  function reportFailure() {
    const msg = 'Could not save order. Please refresh and try again.';
    if (typeof showMessage === 'function') {
      showMessage('error', msg);
    } else {
      console.error('[media_reorder] ' + msg);
    }
    document.dispatchEvent(new CustomEvent('save:end', { detail: { ok: false } }));
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-media-reorder]').forEach(initContainer);
  });
})();
