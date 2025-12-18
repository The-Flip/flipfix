/**
 * Searchable Dropdown Factory
 *
 * Creates searchable dropdowns with common behavior:
 * - Toggle show/hide on edit button click
 * - Focus search input when shown
 * - Load data on first show (cached for subsequent opens)
 * - Filter and render on search input
 * - Keyboard navigation (via dropdown_keyboard.js)
 * - Click outside to close
 *
 * Requires: dropdown_keyboard.js
 *
 * Usage:
 *   createSearchableDropdown({
 *     wrapper: element,
 *     loadData: async () => fetchedData,
 *     renderItems: (data, query) => htmlString,
 *     onSelect: async (value) => { ... },
 *   });
 */

function createSearchableDropdown(config) {
  const { wrapper, loadData, renderItems, onSelect } = config;

  const editBtns = wrapper.querySelectorAll('[data-edit-btn]');
  const dropdown = wrapper.querySelector('[data-dropdown]');
  const searchInput = wrapper.querySelector('[data-search]');
  const listContainer = wrapper.querySelector('[data-list]');

  if (!editBtns.length || !dropdown || !searchInput || !listContainer) return null;

  let data = null;
  let isVisible = false;

  // Keyboard navigation
  const keyboardNav = attachDropdownKeyboard({
    searchInput,
    listContainer,
    getSelectableItems: () => listContainer.querySelectorAll('[data-value]'),
    onSelect: (item) => handleSelect(item.dataset.value),
    onEscape: hide,
  });

  function hide() {
    dropdown.classList.add('hidden');
    isVisible = false;
  }

  function show() {
    dropdown.classList.remove('hidden');
    isVisible = true;
    searchInput.value = '';
    searchInput.focus();
    if (data === null) {
      load();
    } else {
      render('');
    }
  }

  async function load() {
    try {
      data = await loadData();
      render('');
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  }

  function render(query) {
    listContainer.innerHTML = renderItems(data, query);
    listContainer.querySelectorAll('[data-value]').forEach((item) => {
      item.addEventListener('click', () => handleSelect(item.dataset.value));
    });
    keyboardNav.reset();
  }

  async function handleSelect(value) {
    try {
      const result = await onSelect(value);
      // Return false from onSelect to keep dropdown open
      if (result !== false) {
        hide();
      }
    } catch (error) {
      console.error('Selection failed:', error);
      alert('Operation failed. Please try again.');
    }
  }

  // Event listeners
  editBtns.forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      isVisible ? hide() : show();
    });
  });

  searchInput.addEventListener('input', (e) => {
    render(e.target.value);
  });

  document.addEventListener('click', (e) => {
    if (!wrapper.contains(e.target)) {
      hide();
    }
  });

  return { show, hide };
}
