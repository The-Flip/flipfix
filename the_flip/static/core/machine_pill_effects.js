/**
 * Machine pill side effects — toast messages and confetti.
 *
 * Listens for `pill:updated` events dispatched by settable_pill.js and
 * handles machine-specific side effects:
 *   - operational_status: toast with styled pill
 *   - location: toast (with confetti for "Floor" celebration)
 *
 * Mobile button sync is handled by settable_pill.js via the unified
 * ``syncPillUI`` function (button triggers use ``data-trigger-style="button"``).
 *
 * Used on both machine_feed.html and machine_edit.html.
 *
 * Depends on globals from core.js: showMessage(), escapeHtml(), launchConfetti().
 * Depends on readPillStyling() from settable_pill.js.
 */
(function () {
  'use strict';

  if (typeof document !== 'undefined') {
    document.addEventListener('pill:updated', (event) => {
      const { field, label, data } = event.detail;
      const machineName = escapeHtml(
        document.querySelector('.sidebar__title')?.textContent?.trim() || 'Machine'
      );

      if (field === 'operational_status') {
        const { pillClass, iconClass } = readPillStyling('operational_status');
        const iconHtml = iconClass ? `<i class="fa-solid ${iconClass} meta"></i> ` : '';
        const pillHtml = `<span class="pill ${pillClass}">${iconHtml}${escapeHtml(label)}</span>`;
        showMessage('success', `Status of ${machineName} set to ${pillHtml}`);
      } else if (field === 'location') {
        const pillHtml = `<span class="pill pill--neutral"><i class="fa-solid fa-location-dot meta"></i> ${escapeHtml(label)}</span>`;
        if (data.celebration) {
          showMessage('success', `🎉🎊 ${machineName} moved to ${pillHtml}! 🎊🎉`);
          launchConfetti();
        } else {
          showMessage('success', `Location of ${machineName} set to ${pillHtml}`);
        }
      }
    });
  }
})();
