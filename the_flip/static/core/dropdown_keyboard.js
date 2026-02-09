/**
 * Dropdown Keyboard Navigation
 *
 * Shared utility for keyboard navigation in searchable dropdowns.
 * Handles ArrowUp/Down, Enter to select, Escape to close.
 *
 * Usage:
 *   const nav = attachDropdownKeyboard({
 *     searchInput: inputElement,
 *     listContainer: listElement,
 *     getSelectableItems: () => listContainer.querySelectorAll("[data-value]"),
 *     onSelect: (item) => handleSelect(item.dataset.value),
 *     onEscape: () => hideDropdown(),
 *   });
 *
 *   // Call nav.reset() when re-rendering the list to reset activeIndex
 *   // Call nav.destroy() to remove the keydown listener (prevents stacking)
 */
(function (exports) {
  'use strict';

  // ── Core ──────────────────────────────────────────────────────

  function attachDropdownKeyboard(config) {
    const { searchInput, listContainer, getSelectableItems, onSelect, onEscape } = config;

    let activeIndex = -1;

    function getItems() {
      return Array.from(getSelectableItems());
    }

    function updateActiveState() {
      const items = getItems();
      items.forEach((item, index) => {
        if (index === activeIndex) {
          item.classList.add('dropdown-active');
          item.scrollIntoView({ block: 'nearest' });
        } else {
          item.classList.remove('dropdown-active');
        }
      });
    }

    function reset() {
      activeIndex = -1;
      updateActiveState();
    }

    function handleKeydown(event) {
      const items = getItems();
      if (!items.length) {
        if (event.key === 'Escape') {
          onEscape();
        } else if (event.key === 'Enter') {
          event.preventDefault();
        }
        return;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        const dropdown = listContainer.closest('.link-dropdown');
        if (dropdown) dropdown.classList.add('keyboard-navigating');
        activeIndex = Math.min(activeIndex + 1, items.length - 1);
        updateActiveState();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        const dropdown = listContainer.closest('.link-dropdown');
        if (dropdown) dropdown.classList.add('keyboard-navigating');
        activeIndex = Math.max(activeIndex - 1, 0);
        updateActiveState();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        if (activeIndex >= 0 && activeIndex < items.length) {
          onSelect(items[activeIndex]);
        }
      } else if (event.key === 'Escape') {
        onEscape();
      }
    }

    searchInput.addEventListener('keydown', handleKeydown);

    return {
      reset,
      destroy: function () {
        searchInput.removeEventListener('keydown', handleKeydown);
      },
    };
  }

  // ── Exports ───────────────────────────────────────────────────

  // Browser: expose as global (consumed by link_autocomplete.js)
  if (typeof window !== 'undefined') {
    window.attachDropdownKeyboard = attachDropdownKeyboard;
  }

  // Node: export for tests
  if (exports) {
    exports.attachDropdownKeyboard = attachDropdownKeyboard;
  }
})(typeof module !== 'undefined' ? module.exports : null);
