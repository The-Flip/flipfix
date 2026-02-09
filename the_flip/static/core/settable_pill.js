/**
 * Settable Pill — unified AJAX dropdown handler for all settable pills.
 *
 * A settable pill is a clickable pill/badge that opens a dropdown menu
 * to change a field value via AJAX. This module provides the shared
 * plumbing: AJAX POST, pill UI sync, dropdown selected-state sync,
 * and timeline entry injection.
 *
 * ## Data-attribute contract
 *
 * Pill trigger (the visible button):
 *   data-pill-field  — POST field name (e.g. "status", "operational_status")
 *   data-action      — POST action value (e.g. "update_status")
 *
 * Dropdown items (the choices):
 *   data-value       — field value to POST
 *   data-label       — display label (fallback if server doesn't return one)
 *   data-pill-class  — (optional) CSS class to apply to pill trigger
 *   data-icon        — (optional) FA icon class to apply to pill trigger icon
 *
 * Wrapper ancestor:
 *   data-update-url  — AJAX endpoint URL
 *
 * ## Events
 *
 * Dispatches `pill:updated` on the wrapper element (bubbles) after a
 * successful update. Listeners receive:
 *   detail.field  — field name
 *   detail.value  — new value
 *   detail.label  — display label (from server response or data-label)
 *   detail.data   — full server response object
 *
 * Depends on globals from core.js: getCsrfToken(), showMessage(),
 * injectFeedEntry().
 */
(function () {
  'use strict';

  /**
   * POST a field update and sync all matching pills on the page.
   * @param {HTMLElement} item - The clicked dropdown__item
   * @param {HTMLElement} trigger - The pill trigger button with [data-pill-field]
   */
  function updateSettablePill(item, trigger) {
    const field = trigger.dataset.pillField;
    const action = trigger.dataset.action;
    const value = item.dataset.value;
    const label = item.dataset.label;

    const dropdown = item.closest('.dropdown');
    const wrapper = dropdown.closest('[data-update-url]');
    if (!wrapper) return;

    const updateUrl = wrapper.dataset.updateUrl;

    // Close dropdown immediately
    const menu = dropdown.querySelector('.dropdown__menu');
    if (menu) menu.classList.add('hidden');
    const expandedBtn = dropdown.querySelector('[aria-expanded]');
    if (expandedBtn) expandedBtn.setAttribute('aria-expanded', 'false');

    // POST the update
    const formData = new FormData();
    formData.append('action', action);
    formData.append(field, value);

    fetch(updateUrl, {
      method: 'POST',
      body: formData,
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCsrfToken(),
      },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Server error (${res.status})`);
        return res.json();
      })
      .then((data) => {
        if (data.status === 'noop') return;
        if (data.status === 'success') {
          // Prefer server-provided display label, fall back to data-label
          const displayLabel = findDisplayLabel(data, field) || label;

          syncPillUI(updateUrl, field, value, displayLabel, item);
          syncDropdownSelection(updateUrl, field, value);
          injectFeedEntry(data);

          wrapper.dispatchEvent(
            new CustomEvent('pill:updated', {
              bubbles: true,
              detail: { field, value, label: displayLabel, data },
            })
          );
        } else {
          showMessage('error', data.error || 'Error saving change');
        }
      })
      .catch(() => showMessage('error', 'Error saving change'));
  }

  /**
   * Extract the display label from a server response.
   *
   * Endpoints return the display value under various keys:
   *   - problem_report_detail: "new_status_display", "new_priority_display"
   *   - machine_inline_update: "status_display", "location_display"
   *   - part_request_detail:   "new_status_display"
   *
   * The operational_ prefix strip handles machine status, where the field
   * is "operational_status" but the response key is "status_display".
   *
   * @param {Object} data - Server response JSON
   * @param {string} field - The field name
   * @returns {string|null} Display label or null
   */
  function findDisplayLabel(data, field) {
    return (
      data[`${field}_display`] ||
      data[`new_${field}_display`] ||
      data[`${field.replace('operational_', '')}_display`] ||
      null
    );
  }

  /**
   * Update all triggers for a field within the same update-url scope.
   *
   * Handles both pill-style triggers (default) and button-style triggers
   * (identified by ``data-trigger-style="button"``).  Button triggers use
   * ``data-btn-class`` for variant styling and ``.status-icon`` for icon
   * updates; pill triggers use ``data-pill-class`` and ``[data-pill-icon]``.
   *
   * @param {string} updateUrl - The update URL to scope to
   * @param {string} field - The pill field name
   * @param {string} value - The new value
   * @param {string} label - The display label
   * @param {HTMLElement} item - The clicked dropdown item (source of visual data)
   */
  function syncPillUI(updateUrl, field, value, label, item) {
    const pillClass = item.dataset.pillClass;
    const btnClass = item.dataset.btnClass;
    const iconClass = item.dataset.icon;

    const wrappers = document.querySelectorAll(`[data-update-url="${updateUrl}"]`);
    wrappers.forEach((w) => {
      w.querySelectorAll(`[data-pill-field="${field}"]`).forEach((trigger) => {
        if (trigger.dataset.triggerStyle === 'button') {
          // Button trigger: swap btn--* variant class
          if (btnClass) {
            const kept = [...trigger.classList].filter(
              (c) => !c.startsWith('btn--status-') && !c.startsWith('btn--priority-')
            );
            trigger.className = kept.join(' ') + ' ' + btnClass;
          }
          // Update icon
          if (iconClass) {
            const iconEl = trigger.querySelector('.status-icon');
            if (iconEl) {
              const kept = [...iconEl.classList].filter(
                (c) => !c.startsWith('fa-') || c === 'fa-solid'
              );
              iconEl.className = kept.join(' ') + ' fa-' + iconClass;
            }
          }
          // Update tooltip
          const prefix = trigger.dataset.titlePrefix;
          if (prefix) trigger.title = prefix + label;
        } else {
          // Pill trigger: existing logic
          const labelEl = trigger.querySelector('[data-pill-label]');
          if (labelEl) labelEl.textContent = label;

          if (pillClass) {
            const kept = [...trigger.classList].filter((c) => !c.startsWith('pill--'));
            trigger.className = kept.join(' ') + ' ' + pillClass;
          }

          if (iconClass) {
            const iconEl = trigger.querySelector('[data-pill-icon]');
            if (iconEl) {
              const kept = [...iconEl.classList].filter(
                (c) => !c.startsWith('fa-') || c === 'fa-solid'
              );
              iconEl.className = kept.join(' ') + ' fa-' + iconClass;
            }
          }
        }
      });
    });
  }

  /**
   * Sync dropdown__item--selected state and aria-checked across all matching dropdowns.
   * @param {string} updateUrl - The update URL to scope to
   * @param {string} field - The pill field name
   * @param {string} value - The newly selected value
   */
  function syncDropdownSelection(updateUrl, field, value) {
    const wrappers = document.querySelectorAll(`[data-update-url="${updateUrl}"]`);
    wrappers.forEach((w) => {
      // Find dropdowns whose trigger matches this field
      w.querySelectorAll(`[data-pill-field="${field}"]`).forEach((trigger) => {
        const dropdown = trigger.closest('.dropdown');
        if (!dropdown) return;
        dropdown.querySelectorAll('.dropdown__item').forEach((item) => {
          const selected = item.dataset.value === value;
          item.classList.toggle('dropdown__item--selected', selected);
          if (item.hasAttribute('aria-checked')) {
            item.setAttribute('aria-checked', String(selected));
          }
        });
      });
    });
  }

  /**
   * Read the current visual styling of a pill from the DOM.
   *
   * Useful in pill:updated listeners that need to build toast HTML
   * reflecting the pill's current appearance. Call this AFTER syncPillUI
   * has run (i.e. inside a pill:updated listener).
   *
   * @param {string} field - The data-pill-field value (e.g. "operational_status")
   * @returns {{ pillClass: string, iconClass: string|null }}
   */
  function readPillStyling(field) {
    const el = document.querySelector(`.pill[data-pill-field="${field}"]`);
    const pillClass = el
      ? [...el.classList].find((c) => c.startsWith('pill--')) || 'pill--neutral'
      : 'pill--neutral';
    const iconEl = el?.querySelector('[data-pill-icon]');
    const iconClass = iconEl
      ? [...iconEl.classList].find((c) => c.startsWith('fa-') && c !== 'fa-solid') || null
      : null;
    return { pillClass, iconClass };
  }

  // Expose readPillStyling for page-specific pill:updated listeners
  if (typeof window !== 'undefined') {
    window.readPillStyling = readPillStyling;
  }

  // Event delegation: handle clicks on dropdown items inside settable pills
  if (typeof document !== 'undefined') {
    document.addEventListener('click', (event) => {
      const item = event.target.closest('.dropdown__item');
      if (!item) return;
      const dropdown = item.closest('.dropdown');
      if (!dropdown) return;
      const trigger = dropdown.querySelector('[data-pill-field]');
      if (trigger) {
        event.stopPropagation(); // Prevent the global dropdown-close listener
        updateSettablePill(item, trigger);
      }
    });
  }

  // Export for testing
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      updateSettablePill,
      syncPillUI,
      syncDropdownSelection,
      findDisplayLabel,
      readPillStyling,
    };
  }
})();
