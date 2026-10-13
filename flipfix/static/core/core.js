/**
 * Core JavaScript utilities for The Flip.
 * Loaded on all pages via base.html.
 */

/* ==========================================================================
   Utilities
   ========================================================================== */

/**
 * Format Date as datetime-local input value (YYYY-MM-DDTHH:MM).
 * Used for initializing datetime-local inputs with current time or converting UTC to local.
 * @param {Date} date - The date to format
 * @returns {string} Formatted string for datetime-local input value
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
 * Display a toast-style message at the top of the page.
 * @param {string} kind - Message type: 'success', 'error', 'info', 'warning'
 * @param {string} text - Message content (can include HTML)
 */
function showMessage(kind, text) {
  let container = document.querySelector('.messages');
  if (!container) {
    const main = document.querySelector('.main-content') || document.body;
    container = document.createElement('div');
    container.className = 'messages';
    main.prepend(container);
  }
  const msg = document.createElement('div');
  msg.className = `message message--${kind}`;
  msg.innerHTML = text;
  container.appendChild(msg);
}

/**
 * Get the CSRF token from cookies for AJAX requests.
 * @returns {string} The CSRF token value
 */
function getCsrfToken() {
  const match = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
  return match ? match.split('=')[1] : '';
}

/**
 * Escape a string for safe interpolation into innerHTML / template literals.
 * @param {string} str - Untrusted string
 * @returns {string} HTML-safe string
 */
function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Apply an edit descriptor to a textarea, preserving the undo stack.
 *
 * The descriptor is { replaceStart, replaceEnd, replacement, selectionStart,
 * selectionEnd }: replace replaceStart..replaceEnd with replacement, then set
 * the selection. Uses execCommand('insertText') to keep Cmd/Ctrl+Z working;
 * despite being "deprecated", it remains the only way to programmatically
 * edit a textarea with undo support. execCommand edits the *focused* element,
 * so when the textarea isn't focused (e.g. an async upload finished after the
 * user moved on), or in environments without it (jsdom), this falls back to
 * direct .value assignment.
 *
 * @param {HTMLTextAreaElement} textarea
 * @param {object|null} result - Edit descriptor; null is a no-op
 * @returns {boolean} Whether an edit was applied
 */
function applyTextareaEdit(textarea, result) {
  if (!result) return false;

  textarea.selectionStart = result.replaceStart;
  textarea.selectionEnd = result.replaceEnd;
  const doc = textarea.ownerDocument;
  if (doc.activeElement !== textarea || !doc.execCommand('insertText', false, result.replacement)) {
    const before = textarea.value.substring(0, result.replaceStart);
    const after = textarea.value.substring(result.replaceEnd);
    textarea.value = `${before}${result.replacement}${after}`;
  }

  textarea.selectionStart = result.selectionStart;
  textarea.selectionEnd = result.selectionEnd;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
}

/* ==========================================================================
   Dropdowns
   ========================================================================== */

/** @type {WeakMap<HTMLElement, AbortController>} */
const _menuControllers = new WeakMap();

/**
 * Close all open dropdown menus and clean up keyboard handlers.
 */
function closeAllDropdowns() {
  document.querySelectorAll('.dropdown__menu').forEach(function (menu) {
    menu.classList.add('hidden');
    const controller = _menuControllers.get(menu);
    if (controller) {
      controller.abort();
      _menuControllers.delete(menu);
    }
    const btn = menu.closest('.dropdown').querySelector('[aria-expanded]');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  });
}

/**
 * Toggle a dropdown menu open/closed.
 * For menus with role="menu", activates keyboard navigation and focus
 * management per the WAI-ARIA Menu Button pattern.
 * @param {HTMLElement} button - The button that triggers the dropdown
 */
function toggleDropdown(button) {
  const dropdown = button.closest('.dropdown');
  const menu = dropdown.querySelector('.dropdown__menu');
  const isOpen = !menu.classList.contains('hidden');

  closeAllDropdowns();

  if (!isOpen) {
    menu.classList.remove('hidden');
    button.setAttribute('aria-expanded', 'true');
    if (menu.getAttribute('role') === 'menu') {
      _activateMenuKeyboard(menu, button);
    }
  }
}

/**
 * Activate keyboard navigation for an open role="menu" dropdown.
 * Handles ArrowUp/Down, Home/End, Enter/Space, Escape, and Tab
 * per the WAI-ARIA Menu Button pattern.
 * @param {HTMLElement} menu - The menu element with role="menu"
 * @param {HTMLElement} trigger - The trigger button
 */
function _activateMenuKeyboard(menu, trigger) {
  const old = _menuControllers.get(menu);
  if (old) old.abort();

  const controller = new AbortController();
  _menuControllers.set(menu, controller);

  const items = Array.from(menu.querySelectorAll('[role="menuitemradio"], [role="menuitem"]'));
  if (!items.length) return;

  // Focus the checked item, or the first item
  const checked = items.find((item) => item.getAttribute('aria-checked') === 'true');
  (checked || items[0]).focus();

  menu.addEventListener(
    'keydown',
    (event) => {
      const currentIndex = items.indexOf(document.activeElement);

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          items[(currentIndex + 1) % items.length].focus();
          break;
        case 'ArrowUp':
          event.preventDefault();
          items[(currentIndex - 1 + items.length) % items.length].focus();
          break;
        case 'Home':
          event.preventDefault();
          items[0].focus();
          break;
        case 'End':
          event.preventDefault();
          items[items.length - 1].focus();
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          if (currentIndex >= 0) items[currentIndex].click();
          trigger.focus();
          controller.abort();
          _menuControllers.delete(menu);
          break;
        case 'Escape':
          event.preventDefault();
          event.stopPropagation();
          closeAllDropdowns();
          trigger.focus();
          break;
        case 'Tab':
          closeAllDropdowns();
          break;
      }
    },
    { signal: controller.signal }
  );
}

// Close dropdowns when clicking outside
if (typeof document !== 'undefined') {
  document.addEventListener('click', function (event) {
    if (!event.target.closest('.dropdown')) {
      closeAllDropdowns();
    }
  });
}

// Keyboard support: Escape to close all, ArrowDown/Up to open from trigger
if (typeof document !== 'undefined') {
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeAllDropdowns();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const trigger = event.target.closest('[aria-haspopup]');
      if (trigger && trigger.getAttribute('aria-expanded') !== 'true') {
        event.preventDefault();
        toggleDropdown(trigger);
      }
    }
  });
}

/* ==========================================================================
   Clickable Cards
   ========================================================================== */

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    function bindCard(card) {
      const targetUrl = card.dataset.url;
      if (!targetUrl || card.dataset.clickableBound === 'true') return;
      card.dataset.clickableBound = 'true';

      const navigate = () => {
        window.location.href = targetUrl;
      };

      card.addEventListener('click', navigate);
      card.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          navigate();
        }
      });
    }

    document.querySelectorAll('.js-clickable-card').forEach(bindCard);

    document.addEventListener('card:initialize', (event) => {
      const node = event.detail;
      if (node && node.classList && node.classList.contains('js-clickable-card')) {
        bindCard(node);
      }
      if (node && node.querySelectorAll) {
        node.querySelectorAll('.js-clickable-card').forEach(bindCard);
      }
    });
  });
}

/* ==========================================================================
   Smart Dates (relative time formatting)
   ========================================================================== */

function formatTime(date) {
  const minutes = date.getMinutes();
  const formatter = new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: minutes === 0 ? undefined : '2-digit',
  });
  return formatter.format(date).toLowerCase();
}

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatRelative(date) {
  const now = new Date();
  const diffMs = now - date;
  const oneDay = 24 * 60 * 60 * 1000;

  const sameDay = isSameDay(date, now);
  const yesterday = isSameDay(date, new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));

  if (sameDay) {
    return formatTime(date);
  }

  if (yesterday) {
    return `Yesterday ${formatTime(date)}`;
  }

  if (diffMs < 7 * oneDay) {
    const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(date);
    return `${weekday} ${formatTime(date)}`;
  }

  if (date.getFullYear() === now.getFullYear()) {
    const monthDay = new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
    }).format(date);
    return `${monthDay} ${formatTime(date)}`;
  }

  const full = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
  return `${full} ${formatTime(date)}`;
}

function applySmartDates(root = document) {
  const dateNodes = root.querySelectorAll('.smart-date');
  dateNodes.forEach((node) => {
    const iso = node.getAttribute('datetime');
    if (!iso) return;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return;

    node.textContent = formatRelative(date);
  });
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => applySmartDates());
}

/* ==========================================================================
   Timeline Injection
   ========================================================================== */

/**
 * Inject a new entry into the feed timeline if the timeline accepts this entry type.
 * Looks for a timeline with data-entry-types attribute that includes the entry_type
 * from the AJAX response.
 * @param {Object} data - Response data with log_entry_html and entry_type fields
 */
function injectFeedEntry(data) {
  if (!data.log_entry_html || !data.entry_type) return;

  const timelines = document.querySelectorAll('.timeline[data-entry-types]');
  for (const timeline of timelines) {
    const acceptedTypes = timeline.dataset.entryTypes.split(',').map((t) => t.trim());
    if (acceptedTypes.includes(data.entry_type)) {
      const timelineLine = timeline.querySelector('.timeline__line');
      if (timelineLine) {
        timelineLine.insertAdjacentHTML('afterend', data.log_entry_html);
        applySmartDates(timelineLine.nextElementSibling);
      }
      break;
    }
  }
}

/* ==========================================================================
   Confetti Celebration
   ========================================================================== */

/**
 * Dynamically load and launch confetti animation.
 * Only loads the library on first use to avoid impacting page load.
 */
function launchConfetti() {
  if (window.confetti) {
    fireConfetti();
    return;
  }
  const script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.3/dist/confetti.browser.min.js';
  script.onload = fireConfetti;
  document.head.appendChild(script);
}

/**
 * Fire confetti bursts from both sides of the screen.
 */
function fireConfetti() {
  confetti({ particleCount: 100, spread: 70, origin: { x: 0.1, y: 0.6 } });
  confetti({ particleCount: 100, spread: 70, origin: { x: 0.9, y: 0.6 } });
}

// Test exports (Node only)
if (typeof module !== 'undefined') {
  module.exports = {
    toDateTimeLocalValue,
    isSameDay,
    formatTime,
    formatRelative,
    escapeHtml,
    applyTextareaEdit,
  };
}
