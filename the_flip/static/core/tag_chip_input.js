/**
 * Tag Chip Input
 *
 * Multi-select chip input for tag selection in wiki page forms.
 * Displays selected tags as removable chips with autocomplete to add more.
 *
 * Requires: dropdown_keyboard.js (for keyboard navigation)
 *
 * Usage:
 *   <div data-tag-chip-input data-autocomplete-url="/api/wiki/tags/">
 *     <div class="chip-input">
 *       <div data-chip-container></div>
 *       <input type="text" data-chip-search class="chip-input__search"
 *              placeholder="Add tag...">
 *     </div>
 *     <div class="autocomplete__dropdown hidden"></div>
 *   </div>
 *
 * Data attributes:
 *   data-autocomplete-url: API endpoint for tag list (required)
 *   data-initial-tags: Comma-separated tags to pre-populate
 */

(function () {
  'use strict';

  function initTagChipInput(container) {
    const chipContainer = container.querySelector('[data-chip-container]');
    const searchInput = container.querySelector('[data-chip-search]');
    const dropdown = container.querySelector('.autocomplete__dropdown');
    const endpoint = container.dataset.autocompleteUrl;

    if (!chipContainer || !searchInput || !dropdown || !endpoint) return;

    let allTags = [];
    const selectedTags = new Set();
    let _programmatic = false;

    // Prefetch all tags on init (typically small dataset)
    fetch(endpoint)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => {
        allTags = data.tags || [];
        // Render initial chips after tags are loaded
        renderInitialChips();
      })
      .catch(() => {
        allTags = [];
        // Still try to render initial chips
        renderInitialChips();
      });

    // Keyboard navigation for dropdown
    const keyboardNav = attachDropdownKeyboard({
      searchInput: searchInput,
      listContainer: dropdown,
      getSelectableItems: () => dropdown.querySelectorAll('[data-tag]'),
      onSelect: (item) => {
        addTagChip(item.dataset.tag);
      },
      onEscape: hideDropdown,
    });

    function hideDropdown() {
      dropdown.classList.add('hidden');
      dropdown.innerHTML = '';
    }

    function filterTags(query) {
      const q = query.toLowerCase().trim();
      // Filter out already-selected tags
      let filtered = allTags.filter((tag) => !selectedTags.has(tag));
      if (!q) return filtered;
      return filtered.filter((tag) => tag.toLowerCase().includes(q));
    }

    function renderDropdown(list) {
      if (!list.length) {
        hideDropdown();
        return;
      }
      dropdown.innerHTML = '';

      list.forEach((tag) => {
        const item = document.createElement('div');
        item.className = 'autocomplete__item';
        item.dataset.tag = tag;
        item.textContent = tag;

        item.addEventListener('mousedown', (event) => {
          event.preventDefault();
          addTagChip(tag);
        });

        dropdown.appendChild(item);
      });

      dropdown.classList.remove('hidden');
      keyboardNav.reset();
    }

    function createChip(tag) {
      const chip = document.createElement('span');
      chip.className = 'pill pill--removable pill--neutral';
      chip.dataset.tag = tag;

      const text = document.createElement('span');
      text.className = 'pill__text';
      text.textContent = tag;
      chip.appendChild(text);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'pill__remove';
      removeBtn.setAttribute('aria-label', `Remove ${tag}`);
      removeBtn.innerHTML = '&times;';
      removeBtn.addEventListener('click', () => removeChip(chip, tag));
      chip.appendChild(removeBtn);

      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'tags';
      hidden.value = tag;
      chip.appendChild(hidden);

      return chip;
    }

    function addTagChip(tag) {
      const trimmed = tag.trim();
      if (!trimmed || selectedTags.has(trimmed)) return;

      // Normalize: convert to lowercase with hyphens (basic slugification)
      const normalized = trimmed
        .toLowerCase()
        .replace(/\s+/g, '-')
        .replace(/[^a-z0-9\-\/]/g, '');

      if (!normalized || selectedTags.has(normalized)) return;

      selectedTags.add(normalized);
      const chip = createChip(normalized);
      chipContainer.appendChild(chip);

      // Clear search and hide dropdown
      searchInput.value = '';
      hideDropdown();
      if (!_programmatic) {
        searchInput.focus();
      }
    }

    function removeChip(chip, tag) {
      selectedTags.delete(tag);
      chip.remove();
      searchInput.focus();
    }

    function renderInitialChips() {
      // Remove fallback hidden inputs
      chipContainer.querySelectorAll('[data-fallback-input]').forEach((input) => input.remove());

      // Load initial tags from data attribute
      const initialTags = container.dataset.initialTags;
      if (initialTags) {
        initialTags.split(',').forEach((tag) => {
          const trimmed = tag.trim();
          if (trimmed && !selectedTags.has(trimmed)) {
            selectedTags.add(trimmed);
            const chip = createChip(trimmed);
            chipContainer.appendChild(chip);
          }
        });
      }
    }

    function showDropdown() {
      const filtered = filterTags(searchInput.value);
      renderDropdown(filtered);
    }

    // Show dropdown on focus
    searchInput.addEventListener('focus', showDropdown);

    // Also show on click
    searchInput.addEventListener('click', showDropdown);

    searchInput.addEventListener('input', () => {
      const filtered = filterTags(searchInput.value);
      renderDropdown(filtered);
    });

    searchInput.addEventListener('keydown', (event) => {
      // Enter: add as new tag if not selecting from dropdown
      if (event.key === 'Enter' && searchInput.value.trim()) {
        // If dropdown is visible and has active item, let dropdown_keyboard handle it
        const activeItem = dropdown.querySelector('.dropdown-active');
        if (!activeItem) {
          event.preventDefault();
          addTagChip(searchInput.value);
        }
      }

      // Backspace: remove last chip if search is empty
      if (event.key === 'Backspace' && !searchInput.value) {
        const chips = chipContainer.querySelectorAll('.pill');
        if (chips.length > 0) {
          const lastChip = chips[chips.length - 1];
          const tag = lastChip.dataset.tag;
          selectedTags.delete(tag);
          lastChip.remove();
        }
      }
    });

    // Click on container focuses search input
    container.querySelector('.chip-input').addEventListener('click', (event) => {
      if (event.target === event.currentTarget || event.target.matches('[data-chip-container]')) {
        searchInput.focus();
      }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (event) => {
      if (!container.contains(event.target)) {
        hideDropdown();
      }
    });

    // Expose public API on the container element for programmatic use
    container.tagChipInput = {
      addTag(tag) {
        _programmatic = true;
        addTagChip(tag);
        _programmatic = false;
      },
      clearAll() {
        chipContainer.querySelectorAll('.pill').forEach((chip) => {
          const tag = chip.dataset.tag;
          selectedTags.delete(tag);
          chip.remove();
        });
      },
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const containers = document.querySelectorAll('[data-tag-chip-input]');
    containers.forEach((container) => initTagChipInput(container));
  });
})();
