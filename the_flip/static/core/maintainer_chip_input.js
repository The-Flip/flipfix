/**
 * Maintainer Chip Input
 *
 * Multi-select chip input for maintainer selection in log entry forms.
 * Displays selected maintainers as removable chips with autocomplete to add more.
 *
 * Requires: dropdown_keyboard.js (for keyboard navigation)
 *
 * Usage:
 *   <div data-maintainer-chip-input data-autocomplete-url="/api/maintainers/">
 *     <div class="chip-input">
 *       <div data-chip-container></div>
 *       <input type="text" data-chip-search class="chip-input__search"
 *              name="maintainer_freetext" placeholder="Search users...">
 *     </div>
 *     <div class="autocomplete__dropdown hidden"></div>
 *   </div>
 *   <script id="initial-maintainers-data" type="application/json">
 *     [{"username": "alice", "display_name": "Alice Smith"}, ...]
 *   </script>
 *
 * Data attributes:
 *   data-autocomplete-url: API endpoint for maintainer list (required)
 *   data-initial-maintainers-id: ID of script tag containing initial maintainers JSON
 *   data-initial-freetext: Comma-separated freetext names to load as chips
 *   data-form-id: Optional form ID for hidden inputs
 */

(function () {
  'use strict';

  function initMaintainerChipInput(container) {
    const chipContainer = container.querySelector('[data-chip-container]');
    const searchInput = container.querySelector('[data-chip-search]');
    const dropdown = container.querySelector('.autocomplete__dropdown');
    const endpoint = container.dataset.autocompleteUrl;
    const formId = container.dataset.formId || null;

    if (!chipContainer || !searchInput || !dropdown || !endpoint) return;

    let allMaintainers = [];
    const selectedUsernames = new Set();
    const selectedFreetext = new Set();

    // Prefetch all maintainers on init (small dataset)
    fetch(endpoint)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => {
        allMaintainers = data.maintainers || [];
        // Render initial chips after maintainers are loaded
        renderInitialChips();
      })
      .catch(() => {
        allMaintainers = [];
        // Still try to render initial chips (freetext will work)
        renderInitialChips();
      });

    // Keyboard navigation for dropdown
    const keyboardNav = attachDropdownKeyboard({
      searchInput: searchInput,
      listContainer: dropdown,
      getSelectableItems: () => dropdown.querySelectorAll('[data-username]'),
      onSelect: (item) => {
        const maintainer = allMaintainers.find((m) => m.username === item.dataset.username);
        if (maintainer) addMaintainerChip(maintainer);
      },
      onEscape: hideDropdown,
    });

    function hideDropdown() {
      dropdown.classList.add('hidden');
      dropdown.innerHTML = '';
    }

    function formatMaintainer(m) {
      if (m.display_name === m.username) {
        return m.username;
      }
      return `${m.display_name} (${m.username})`;
    }

    function filterMaintainers(query) {
      const q = query.toLowerCase().trim();
      // Filter out already-selected maintainers
      let filtered = allMaintainers.filter((m) => !selectedUsernames.has(m.username));
      if (!q) return filtered;
      return filtered.filter(
        (m) =>
          m.first_name.toLowerCase().startsWith(q) ||
          m.last_name.toLowerCase().startsWith(q) ||
          m.username.toLowerCase().startsWith(q)
      );
    }

    function renderDropdown(list) {
      if (!list.length) {
        hideDropdown();
        return;
      }
      dropdown.innerHTML = '';

      list.forEach((maintainer) => {
        const item = document.createElement('div');
        item.className = 'autocomplete__item';
        item.dataset.username = maintainer.username;
        item.textContent = formatMaintainer(maintainer);

        item.addEventListener('mousedown', (event) => {
          event.preventDefault();
          addMaintainerChip(maintainer);
        });

        dropdown.appendChild(item);
      });

      dropdown.classList.remove('hidden');
      keyboardNav.reset();
    }

    function createChip(displayName, hiddenName, hiddenValue, dataAttr) {
      const chip = document.createElement('span');
      chip.className = 'pill pill--removable pill--neutral';
      chip.setAttribute(dataAttr.name, dataAttr.value);

      const text = document.createElement('span');
      text.className = 'pill__text';
      text.textContent = displayName;
      chip.appendChild(text);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'pill__remove';
      removeBtn.setAttribute('aria-label', `Remove ${displayName}`);
      removeBtn.innerHTML = '&times;';
      removeBtn.addEventListener('click', () => removeChip(chip, hiddenValue, dataAttr.name));
      chip.appendChild(removeBtn);

      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = hiddenName;
      hidden.value = hiddenValue;
      if (formId) hidden.setAttribute('form', formId);
      chip.appendChild(hidden);

      return chip;
    }

    function addMaintainerChip(maintainer) {
      if (selectedUsernames.has(maintainer.username)) return;

      selectedUsernames.add(maintainer.username);
      const chip = createChip(
        maintainer.display_name,
        'maintainer_usernames',
        maintainer.username,
        {
          name: 'data-username',
          value: maintainer.username,
        }
      );
      chipContainer.appendChild(chip);

      // Clear search and hide dropdown
      searchInput.value = '';
      hideDropdown();
      searchInput.focus();
    }

    function addFreetextChip(name) {
      const trimmed = name.trim();
      if (!trimmed || selectedFreetext.has(trimmed)) return;

      // Check if this matches a maintainer username or display name
      const matchingMaintainer = allMaintainers.find(
        (m) =>
          m.username.toLowerCase() === trimmed.toLowerCase() ||
          m.display_name.toLowerCase() === trimmed.toLowerCase()
      );
      if (matchingMaintainer) {
        addMaintainerChip(matchingMaintainer);
        return;
      }

      selectedFreetext.add(trimmed);
      const chip = createChip(trimmed, 'maintainer_freetext', trimmed, {
        name: 'data-freetext',
        value: trimmed,
      });
      chipContainer.appendChild(chip);

      searchInput.value = '';
      hideDropdown();
      searchInput.focus();
    }

    function removeChip(chip, value, attrName) {
      if (attrName === 'data-username') {
        selectedUsernames.delete(value);
      } else {
        selectedFreetext.delete(value);
      }
      chip.remove();
      searchInput.focus();
    }

    function renderInitialChips() {
      // Remove fallback hidden inputs (they're replaced by chip-managed hidden inputs)
      // These inputs ensure data isn't lost if JS fails, but we don't need them once JS runs
      chipContainer.querySelectorAll('[data-fallback-input]').forEach((input) => input.remove());

      // Load initial maintainers from JSON script tag
      const initialDataId = container.dataset.initialMaintainersId;
      if (initialDataId) {
        const scriptTag = document.getElementById(initialDataId);
        if (scriptTag) {
          try {
            const initialMaintainers = JSON.parse(scriptTag.textContent);
            initialMaintainers.forEach((m) => {
              if (!selectedUsernames.has(m.username)) {
                selectedUsernames.add(m.username);
                const chip = createChip(m.display_name, 'maintainer_usernames', m.username, {
                  name: 'data-username',
                  value: m.username,
                });
                chipContainer.appendChild(chip);
              }
            });
          } catch (e) {
            console.error('Failed to parse initial maintainers:', e);
          }
        }
      }

      // Load initial freetext names
      const initialFreetext = container.dataset.initialFreetext;
      if (initialFreetext) {
        initialFreetext.split(',').forEach((name) => {
          const trimmed = name.trim();
          if (trimmed && !selectedFreetext.has(trimmed)) {
            selectedFreetext.add(trimmed);
            const chip = createChip(trimmed, 'maintainer_freetext', trimmed, {
              name: 'data-freetext',
              value: trimmed,
            });
            chipContainer.appendChild(chip);
          }
        });
      }
    }

    // Event listeners
    searchInput.addEventListener('focus', () => {
      const filtered = filterMaintainers(searchInput.value);
      renderDropdown(filtered);
    });

    searchInput.addEventListener('input', () => {
      const filtered = filterMaintainers(searchInput.value);
      renderDropdown(filtered);
    });

    searchInput.addEventListener('keydown', (event) => {
      // Enter: add as freetext if not selecting from dropdown
      if (event.key === 'Enter' && searchInput.value.trim()) {
        // If dropdown is visible and has active item, let dropdown_keyboard handle it
        const activeItem = dropdown.querySelector('.dropdown-active');
        if (!activeItem) {
          event.preventDefault();
          addFreetextChip(searchInput.value);
        }
      }

      // Backspace: remove last chip if search is empty
      if (event.key === 'Backspace' && !searchInput.value) {
        const chips = chipContainer.querySelectorAll('.pill');
        if (chips.length > 0) {
          const lastChip = chips[chips.length - 1];
          const username = lastChip.dataset.username;
          const freetext = lastChip.dataset.freetext;
          if (username) {
            selectedUsernames.delete(username);
          } else if (freetext) {
            selectedFreetext.delete(freetext);
          }
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
  }

  document.addEventListener('DOMContentLoaded', () => {
    const containers = document.querySelectorAll('[data-maintainer-chip-input]');
    containers.forEach((container) => initMaintainerChipInput(container));
  });
})();
