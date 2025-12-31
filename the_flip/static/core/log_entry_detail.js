/**
 * Log Entry Detail Page
 *
 * Handles auto-save for occurred_at and maintainer fields on the log entry detail page.
 * Auto-initializes on DOMContentLoaded by finding elements by ID.
 *
 * Requires: core.js (for getCsrfToken, toDateTimeLocalValue), dropdown_keyboard.js, maintainer_autocomplete.js
 */

(function () {
  /**
   * Show status indicator with message and state
   */
  function showStatus(element, message, state) {
    if (!element) return;
    element.textContent = message;
    element.className = `status-indicator ${state}`;
  }

  /**
   * Clear status indicator after delay
   */
  function clearStatusAfterDelay(element, delay = 2000) {
    setTimeout(() => {
      if (element) {
        element.textContent = '';
        element.className = 'status-indicator';
      }
    }, delay);
  }

  /**
   * Initialize occurred_at auto-save
   */
  function initOccurredAt() {
    const occurredAtInput = document.getElementById('occurred-at');
    const occurredAtStatus = document.getElementById('occurred-at-status');

    if (!occurredAtInput) return;

    // On page load: convert UTC to browser local time
    const utcDateStr = occurredAtInput.dataset.utc;
    if (utcDateStr) {
      const utcDate = new Date(utcDateStr);
      occurredAtInput.value = toDateTimeLocalValue(utcDate);
    }

    occurredAtInput.addEventListener('change', async () => {
      showStatus(occurredAtStatus, 'Saving...', 'saving');

      try {
        const tzOffsetMinutes = new Date().getTimezoneOffset();
        const formData = new FormData();
        formData.append('action', 'update_occurred_at');
        formData.append('occurred_at', occurredAtInput.value);
        formData.append('tz_offset', tzOffsetMinutes);
        formData.append('csrfmiddlewaretoken', getCsrfToken());

        const response = await fetch(window.location.href, {
          method: 'POST',
          body: formData,
        });

        const data = await response.json();
        if (response.ok && data.success) {
          showStatus(occurredAtStatus, 'Saved', 'saved');
          clearStatusAfterDelay(occurredAtStatus);
        } else {
          showStatus(occurredAtStatus, data.error || 'Error saving', 'error');
        }
      } catch (error) {
        console.error('Save error:', error);
        showStatus(occurredAtStatus, 'Error saving', 'error');
      }
    });
  }

  /**
   * Initialize maintainer auto-save
   */
  function initMaintainerSave() {
    const maintainerInput = document.getElementById('maintainer-names');
    const maintainerStatus = document.getElementById('maintainer-save-indicator');

    if (!maintainerInput) return;

    let lastSavedValue = maintainerInput.value;
    let saveInProgress = false;

    async function saveMaintainers() {
      if (saveInProgress) return;

      const newValue = maintainerInput.value.trim();

      // If empty, restore previous value (no server call)
      if (!newValue) {
        maintainerInput.value = lastSavedValue;
        return;
      }

      // Skip if unchanged
      if (newValue === lastSavedValue) return;

      saveInProgress = true;
      showStatus(maintainerStatus, 'Saving...', 'saving');

      try {
        const formData = new FormData();
        formData.append('action', 'update_maintainers');
        formData.append('maintainers', newValue);
        formData.append('csrfmiddlewaretoken', getCsrfToken());

        const response = await fetch(window.location.href, {
          method: 'POST',
          body: formData,
        });

        const data = await response.json();
        if (response.ok && data.success) {
          lastSavedValue = newValue;
          showStatus(maintainerStatus, 'Saved', 'saved');
          clearStatusAfterDelay(maintainerStatus);
        } else {
          maintainerInput.value = lastSavedValue;
          showStatus(maintainerStatus, data.error || 'Error saving', 'error');
        }
      } catch (error) {
        console.error('Save error:', error);
        maintainerInput.value = lastSavedValue;
        showStatus(maintainerStatus, 'Error saving', 'error');
      } finally {
        saveInProgress = false;
      }
    }

    // Listen for autocomplete selection
    const container = document.querySelector('[data-maintainer-autocomplete]');
    if (container) {
      container.addEventListener('maintainer:selected', saveMaintainers);
    }

    maintainerInput.addEventListener('change', saveMaintainers);
    maintainerInput.addEventListener('blur', saveMaintainers);
  }

  document.addEventListener('DOMContentLoaded', () => {
    initOccurredAt();
    initMaintainerSave();
  });
})();
