/**
 * Dropdown toggle functionality
 * Handles opening/closing dropdown menus
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
