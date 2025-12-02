/**
 * Core JavaScript utilities for The Flip.
 * Loaded on all pages via base.html.
 */

/* ==========================================================================
   Utilities
   ========================================================================== */

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
  const match = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
  return match ? match.split('=')[1] : '';
}

/* ==========================================================================
   Dropdowns
   ========================================================================== */

/**
 * Toggle a dropdown menu open/closed.
 * @param {HTMLElement} button - The button that triggers the dropdown
 */
function toggleDropdown(button) {
  const dropdown = button.closest('.dropdown');
  const menu = dropdown.querySelector('.dropdown__menu');
  const isOpen = !menu.classList.contains('hidden');

  // Close all other dropdowns first
  document.querySelectorAll('.dropdown__menu').forEach(function (m) {
    m.classList.add('hidden');
    const btn = m.closest('.dropdown').querySelector('[aria-expanded]');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  });

  // Toggle this dropdown
  if (!isOpen) {
    menu.classList.remove('hidden');
    button.setAttribute('aria-expanded', 'true');
  }
}

// Close dropdowns when clicking outside
document.addEventListener('click', function (event) {
  if (!event.target.closest('.dropdown')) {
    document.querySelectorAll('.dropdown__menu').forEach(function (menu) {
      menu.classList.add('hidden');
      const btn = menu.closest('.dropdown').querySelector('[aria-expanded]');
      if (btn) btn.setAttribute('aria-expanded', 'false');
    });
  }
});

// Close dropdowns on Escape key
document.addEventListener('keydown', function (event) {
  if (event.key === 'Escape') {
    document.querySelectorAll('.dropdown__menu').forEach(function (menu) {
      menu.classList.add('hidden');
      const btn = menu.closest('.dropdown').querySelector('[aria-expanded]');
      if (btn) btn.setAttribute('aria-expanded', 'false');
    });
  }
});

/* ==========================================================================
   Clickable Cards
   ========================================================================== */

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
  const yesterday = isSameDay(
    date,
    new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
  );

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

document.addEventListener('DOMContentLoaded', () => applySmartDates());

/* ==========================================================================
   Machine Field Updates (status/location dropdowns)
   ========================================================================== */

/**
 * Update a machine field via AJAX (status or location).
 * @param {HTMLElement} button - The dropdown item button that was clicked
 */
function updateMachineField(button) {
  const field = button.dataset.field;
  const value = button.dataset.value;
  const label = button.dataset.label;
  const dropdownMenu = button.closest('.dropdown__menu');
  const wrapper = dropdownMenu.parentElement.parentElement;
  const updateUrl = wrapper.dataset.updateUrl;
  if (!updateUrl) return;

  dropdownMenu.classList.add('hidden');

  const formData = new FormData();
  formData.append('action', field === 'operational_status' ? 'update_status' : 'update_location');
  formData.append(field, value);

  fetch(updateUrl, {
    method: 'POST',
    body: formData,
    credentials: 'same-origin',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'X-CSRFToken': getCsrfToken(),
    }
  })
  .then(res => res.json())
  .then(data => {
    if (data.status === 'noop') {
      return;
    } else if (data.status === 'success') {
      const statusClassMap = {
        good: { pill: 'pill--status-good', btn: 'btn--status-good' },
        fixing: { pill: 'pill--status-fixing', btn: 'btn--status-fixing' },
        broken: { pill: 'pill--status-broken', btn: 'btn--status-broken' },
        unknown: { pill: 'pill--neutral', btn: 'btn--secondary' }
      };
      const iconClassMap = {
        good: 'fa-check',
        fixing: 'fa-wrench',
        broken: 'fa-circle-xmark',
        unknown: 'fa-circle-question'
      };
      if (field === 'operational_status') {
        // Update sidebar pill
        const pill = document.getElementById('status-pill');
        if (pill) {
          const labelEl = pill.querySelector('.status-label');
          const iconEl = pill.querySelector('.status-icon');
          labelEl.textContent = label;
          pill.className = 'pill ' + (statusClassMap[value]?.pill || 'pill--neutral');
          iconEl.className = 'fa-solid meta status-icon ' + (iconClassMap[value] || 'fa-circle-question');
        }
        // Update mobile dropdown button
        const mobileBtn = document.querySelector('.status-btn');
        if (mobileBtn) {
          const iconEl = mobileBtn.querySelector('.status-icon');
          mobileBtn.className = 'btn btn--dropdown status-btn ' + (statusClassMap[value]?.btn || 'btn--secondary');
          iconEl.className = 'fa-solid status-icon ' + (iconClassMap[value] || 'fa-circle-question');
        }
        const machineName = document.querySelector('.sidebar__title')?.textContent?.trim() || 'Machine';
        const pillHtml = `<span class="pill ${statusClassMap[value]?.pill || 'pill--neutral'}"><i class="fa-solid ${iconClassMap[value] || 'fa-circle-question'} meta"></i> ${label}</span>`;
        showMessage('success', `Status of ${machineName} set to ${pillHtml}`);
        // Inject the new log entry into the feed
        if (data.log_entry_html) {
          const timelineLine = document.querySelector('.timeline__line');
          if (timelineLine) {
            timelineLine.insertAdjacentHTML('afterend', data.log_entry_html);
            applySmartDates(timelineLine.nextElementSibling);
          }
        }
      } else {
        const pill = document.getElementById('location-pill');
        if (pill) {
          const labelEl = pill.querySelector('.location-label');
          labelEl.textContent = label;
        }
        const machineName = document.querySelector('.sidebar__title')?.textContent?.trim() || 'Machine';
        const pillHtml = `<span class="pill pill--neutral"><i class="fa-solid fa-location-dot meta"></i> ${label}</span>`;
        if (data.celebration) {
          showMessage('success', `🎉🎊 ${machineName} moved to ${pillHtml}! 🎊🎉`);
          launchConfetti();
        } else {
          showMessage('success', `Location of ${machineName} set to ${pillHtml}`);
        }
        // Inject the new log entry into the feed
        if (data.log_entry_html) {
          const timelineLine = document.querySelector('.timeline__line');
          if (timelineLine) {
            timelineLine.insertAdjacentHTML('afterend', data.log_entry_html);
            // Apply smart date formatting to the new entry
            applySmartDates(timelineLine.nextElementSibling);
          }
        }
      }
    } else {
      showMessage('error', 'Error saving change');
    }
  })
  .catch(() => showMessage('error', 'Error saving change'));
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
