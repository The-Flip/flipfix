// Prevents accidental double-submits: once a form marked [data-submit-guard] is
// submitted, its submit button is disabled and relabelled so a slow response
// does not invite a second click. This is a UX safeguard only — the server's
// idempotency token is what actually guarantees no duplicate is created.
(function (exports) {
  'use strict';

  const BUSY_LABEL = 'Logging…';

  function initSubmitGuard(form) {
    form.addEventListener('submit', function () {
      // If HTML5 constraint validation fails, the submit event fires but the
      // browser blocks the POST. Disabling the button here would strand the
      // user on an invalid form, so bail and let the browser show its errors.
      if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
        return;
      }

      const button = form.querySelector('[type="submit"]');
      if (!button) {
        return;
      }

      // Disable on the next tick so the button's value is still included in the
      // submitted payload (a disabled control is not serialised).
      setTimeout(function () {
        button.disabled = true;
        button.textContent = button.dataset.busyLabel || BUSY_LABEL;
      }, 0);
    });
  }

  function init() {
    document.querySelectorAll('[data-submit-guard]').forEach(initSubmitGuard);
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  // Test exports (Node only)
  if (exports) {
    exports.initSubmitGuard = initSubmitGuard;
  }
})(typeof module !== 'undefined' ? module.exports : null);
