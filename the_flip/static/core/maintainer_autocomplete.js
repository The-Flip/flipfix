/**
 * Maintainer Autocomplete
 *
 * Provides autocomplete functionality for maintainer/submitter selection in forms.
 * Uses data attributes for configuration, auto-initializes on DOMContentLoaded.
 *
 * Requires: dropdown_keyboard.js (for keyboard navigation)
 *
 * Usage:
 *   <div data-maintainer-autocomplete data-autocomplete-url="/api/maintainers/">
 *     <input type="text" data-maintainer-search placeholder="Who did the work?">
 *     <div class="autocomplete__dropdown hidden"></div>
 *   </div>
 *
 * Options (data attributes on container):
 *   data-autocomplete-url: API endpoint for maintainer list (required)
 *   data-on-select: Name of global callback function to call after selection (optional)
 */

function initMaintainerAutocomplete(container) {
  const input = container.querySelector("[data-maintainer-search]");
  const dropdown = container.querySelector(".autocomplete__dropdown");
  const endpoint = container.dataset.autocompleteUrl;
  const onSelectCallback = container.dataset.onSelect;

  if (!input || !dropdown || !endpoint) return;

  let maintainers = [];

  // Prefetch all maintainers on init (small dataset)
  fetch(endpoint)
    .then((response) => (response.ok ? response.json() : Promise.reject()))
    .then((data) => {
      maintainers = data.maintainers || [];
    })
    .catch(() => {
      maintainers = [];
    });

  // Keyboard navigation
  const keyboardNav = attachDropdownKeyboard({
    searchInput: input,
    listContainer: dropdown,
    getSelectableItems: () => dropdown.querySelectorAll("[data-username]"),
    onSelect: (item) => {
      const maintainer = maintainers.find(
        (m) => m.username === item.dataset.username
      );
      if (maintainer) selectMaintainer(maintainer);
    },
    onEscape: hideDropdown,
  });

  function hideDropdown() {
    dropdown.classList.add("hidden");
    dropdown.innerHTML = "";
  }

  function selectMaintainer(maintainer) {
    input.value = maintainer.display_name;
    hideDropdown();
    // Call optional callback after selection
    if (onSelectCallback && typeof window[onSelectCallback] === "function") {
      window[onSelectCallback](maintainer, input);
    }
  }

  function formatMaintainer(m) {
    if (m.display_name === m.username) {
      return m.username;
    }
    return `${m.display_name} (${m.username})`;
  }

  function filterMaintainers(query) {
    const q = query.toLowerCase().trim();
    if (!q) return maintainers;
    return maintainers.filter(
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
    dropdown.innerHTML = "";

    list.forEach((maintainer) => {
      const item = document.createElement("div");
      item.className = "autocomplete__item";
      item.dataset.username = maintainer.username;
      item.textContent = formatMaintainer(maintainer);

      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
        selectMaintainer(maintainer);
      });

      dropdown.appendChild(item);
    });

    dropdown.classList.remove("hidden");
    keyboardNav.reset();
  }

  input.addEventListener("focus", () => {
    const filtered = filterMaintainers(input.value);
    renderDropdown(filtered);
  });

  input.addEventListener("input", () => {
    const filtered = filterMaintainers(input.value);
    renderDropdown(filtered);
  });

  document.addEventListener("click", (event) => {
    if (!container.contains(event.target)) {
      hideDropdown();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const containers = document.querySelectorAll("[data-maintainer-autocomplete]");
  containers.forEach((container) => initMaintainerAutocomplete(container));
});
