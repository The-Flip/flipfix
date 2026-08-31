/**
 * Copy Button Module
 *
 * Copies the value of another element to the clipboard.
 *
 * Auto-initializes on elements with [data-copy-target], whose value is a
 * CSS selector for the input to copy from:
 *
 *   <input id="invite-link" value="https://...">
 *   <button data-copy-target="#invite-link" data-copy-status="#invite-link-status">
 *     <span data-copy-label>Copy</span>
 *   </button>
 *   <p id="invite-link-status" data-copy-status role="status" aria-live="polite"></p>
 *
 * The button label flips to "Copied" for a moment, and the outcome is also
 * written to its [data-copy-status] element so screen readers hear it — a
 * label change alone is silent. data-copy-status is optional; omit it and
 * the single status element on the page is used.
 *
 * navigator.clipboard is unavailable outside secure contexts, which on this
 * project means plain-HTTP local development. The execCommand fallback is
 * deprecated but is what keeps the button working there; without it the
 * feature would appear broken to anyone testing over http://.
 */
(function (exports) {
  'use strict';

  const RESET_DELAY_MS = 2000;

  /**
   * Copy text to the clipboard, preferring the async Clipboard API.
   *
   * @param {string} text - Text to copy
   * @param {Document} doc - Document to operate on
   * @returns {Promise<boolean>} Whether the copy succeeded
   */
  async function copyText(text, doc = document) {
    if (doc.defaultView?.navigator?.clipboard) {
      try {
        await doc.defaultView.navigator.clipboard.writeText(text);
        return true;
      } catch {
        // Permission denied or insecure context — fall through.
      }
    }
    return legacyCopy(text, doc);
  }

  /**
   * Clipboard fallback for non-secure contexts.
   *
   * @param {string} text - Text to copy
   * @param {Document} doc - Document to operate on
   * @returns {boolean} Whether the copy succeeded
   */
  function legacyCopy(text, doc) {
    if (typeof doc.execCommand !== 'function') {
      return false;
    }
    const scratch = doc.createElement('textarea');
    scratch.value = text;
    scratch.setAttribute('readonly', '');
    scratch.classList.add('visually-hidden');
    doc.body.appendChild(scratch);
    scratch.select();
    let copied = false;
    try {
      copied = doc.execCommand('copy');
    } catch {
      copied = false;
    }
    scratch.remove();
    return copied;
  }

  /**
   * Wire one copy button.
   *
   * @param {HTMLElement} button - Element carrying [data-copy-target]
   * @param {Document} doc - Document to operate on
   */
  function initCopyButton(button, doc = document) {
    const source = doc.querySelector(button.dataset.copyTarget);
    if (!source) {
      return;
    }
    const label = button.querySelector('[data-copy-label]');
    const originalLabel = label ? label.textContent : '';
    // Scoped per button via [data-copy-status] on the button, so a page with
    // two copy buttons doesn't have the second one announcing into the
    // first one's live region. Falls back to the sole status element when
    // there is only one, which is the common case.
    const status = button.dataset.copyStatus
      ? doc.querySelector(button.dataset.copyStatus)
      : doc.querySelector('[data-copy-status]');
    let resetTimer = null;

    button.addEventListener('click', async () => {
      const copied = await copyText(source.value ?? source.textContent, doc);
      if (label) {
        label.textContent = copied ? 'Copied' : 'Press Ctrl+C';
      }
      if (status) {
        status.textContent = copied
          ? 'Link copied to the clipboard.'
          : "Couldn't copy automatically — the link is selected, press Ctrl+C.";
      }
      if (!copied && typeof source.select === 'function') {
        source.select();
      }

      doc.defaultView?.clearTimeout(resetTimer);
      resetTimer = doc.defaultView?.setTimeout(() => {
        if (label) {
          label.textContent = originalLabel;
        }
        if (status) {
          status.textContent = '';
        }
      }, RESET_DELAY_MS);
    });
  }

  /**
   * Wire every copy button in the document.
   *
   * @param {Document} doc - Document to operate on
   */
  function initCopyButtons(doc = document) {
    doc.querySelectorAll('[data-copy-target]').forEach((button) => initCopyButton(button, doc));
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => initCopyButtons());
    } else {
      initCopyButtons();
    }
  }

  // Test exports (Node only)
  if (exports) {
    exports.copyText = copyText;
    exports.initCopyButton = initCopyButton;
    exports.initCopyButtons = initCopyButtons;
  }
})(typeof module !== 'undefined' ? module.exports : null);
