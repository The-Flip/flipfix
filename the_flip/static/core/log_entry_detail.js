/**
 * Log Entry Detail Page
 *
 * Handles auto-save for work date and maintainer fields on the log entry detail page.
 * Auto-initializes on DOMContentLoaded by finding elements by ID.
 *
 * Requires: core.js (for getCsrfToken), dropdown_keyboard.js, maintainer_autocomplete.js
 */

(function () {
  /**
   * Format Date as datetime-local value (YYYY-MM-DDTHH:MM)
   */
  function toDateTimeLocalValue(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  }

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
   * Initialize work date auto-save
   */
  function initWorkDate() {
    const workDateInput = document.getElementById('work-date');
    const workDateStatus = document.getElementById('work-date-status');

    if (!workDateInput) return;

    // On page load: convert UTC to browser local time
    const utcDateStr = workDateInput.dataset.utc;
    if (utcDateStr) {
      const utcDate = new Date(utcDateStr);
      workDateInput.value = toDateTimeLocalValue(utcDate);
    }

    workDateInput.addEventListener('change', async () => {
      showStatus(workDateStatus, 'Saving...', 'saving');

      try {
        const tzOffsetMinutes = new Date().getTimezoneOffset();
        const formData = new FormData();
        formData.append('action', 'update_work_date');
        formData.append('work_date', workDateInput.value);
        formData.append('tz_offset', tzOffsetMinutes);
        formData.append('csrfmiddlewaretoken', getCsrfToken());

        const response = await fetch(window.location.href, {
          method: 'POST',
          body: formData,
        });

        const data = await response.json();
        if (response.ok && data.success) {
          showStatus(workDateStatus, 'Saved', 'saved');
          clearStatusAfterDelay(workDateStatus);
        } else {
          showStatus(workDateStatus, data.error || 'Error saving', 'error');
        }
      } catch (error) {
        console.error('Save error:', error);
        showStatus(workDateStatus, 'Error saving', 'error');
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
    initWorkDate();
    initMaintainerSave();
  });
})();
