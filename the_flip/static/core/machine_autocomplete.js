/**
 * Machine Autocomplete
 *
 * Provides autocomplete functionality for machine selection in forms.
 * Uses data attributes for configuration, auto-initializes on DOMContentLoaded.
 *
 * Requires: dropdown_keyboard.js (for keyboard navigation)
 *
 * Usage:
 *   <div data-machine-autocomplete data-autocomplete-url="/api/machines/">
 *     <input type="text" data-machine-search placeholder="Search machines...">
 *     <input type="hidden" data-machine-slug-input name="machine_slug">
 *     <div class="autocomplete__dropdown hidden"></div>
 *   </div>
 */

function initMachineAutocomplete(container) {
  const input = container.querySelector('[data-machine-search]');
  const hiddenInput = container.querySelector('[data-machine-slug-input]');
  const dropdown = container.querySelector('.autocomplete__dropdown');
  const endpoint = container.dataset.autocompleteUrl;

  if (!input || !hiddenInput || !dropdown || !endpoint) return;

  let results = [];
  let fetchTimeout = null;
  let abortController = null;

  // Keyboard navigation
  const keyboardNav = attachDropdownKeyboard({
    searchInput: input,
    listContainer: dropdown,
    getSelectableItems: () => dropdown.querySelectorAll('[data-slug]'),
    onSelect: (item) => {
      const machine = results.find((m) => m.slug === item.dataset.slug);
      if (machine) selectMachine(machine);
    },
    onEscape: hideDropdown,
  });

  function hideDropdown() {
    dropdown.classList.add('hidden');
    dropdown.innerHTML = '';
  }

  function selectMachine(machine) {
    input.value = machine.display_name;
    hiddenInput.value = machine.slug;
    const errorMessages = container.parentElement?.querySelectorAll('.field-error');
    if (errorMessages?.length) {
      errorMessages.forEach((el) => el.remove());
    }
    hideDropdown();
  }

  function renderDropdown(list) {
    if (!list.length) {
      hideDropdown();
      return;
    }
    dropdown.innerHTML = '';

    list.forEach((machine) => {
      const item = document.createElement('div');
      item.className = 'autocomplete__item';
      item.dataset.slug = machine.slug;

      const line = document.createElement('div');
      const nameSpan = document.createElement('span');
      nameSpan.textContent = machine.display_name;
      line.appendChild(nameSpan);

      if (machine.location) {
        const separator = document.createTextNode(' · ');
        const locSpan = document.createElement('span');
        locSpan.className = 'text-muted';
        locSpan.textContent = machine.location;
        line.appendChild(separator);
        line.appendChild(locSpan);
      }

      item.appendChild(line);

      item.addEventListener('mousedown', (event) => {
        event.preventDefault();
        selectMachine(machine);
      });

      dropdown.appendChild(item);
    });

    dropdown.classList.remove('hidden');
    keyboardNav.reset();
  }

  function fetchMachines(query) {
    if (fetchTimeout) {
      clearTimeout(fetchTimeout);
    }
    fetchTimeout = setTimeout(() => {
      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();
      const params = new URLSearchParams();
      if (query) {
        params.append('q', query);
      }

      const queryString = params.toString();
      const url = queryString ? `${endpoint}?${queryString}` : endpoint;

      fetch(url, { signal: abortController.signal })
        .then((response) => (response.ok ? response.json() : Promise.reject()))
        .then((data) => {
          results = data.machines || [];
          renderDropdown(results);
        })
        .catch((error) => {
          if (error?.name === 'AbortError') return;
          hideDropdown();
        });
    }, 150);
  }

  input.addEventListener('focus', () => {
    fetchMachines(input.value.trim());
  });

  input.addEventListener('input', () => {
    hiddenInput.value = '';
    fetchMachines(input.value.trim());
  });

  document.addEventListener('click', (event) => {
    if (!container.contains(event.target)) {
      hideDropdown();
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const containers = document.querySelectorAll('[data-machine-autocomplete]');
  containers.forEach((container) => initMachineAutocomplete(container));
});
