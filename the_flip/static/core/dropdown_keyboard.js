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
 */

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
      }
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      updateActiveState();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      updateActiveState();
    } else if (event.key === 'Enter') {
      if (activeIndex >= 0 && activeIndex < items.length) {
        event.preventDefault();
        onSelect(items[activeIndex]);
      }
    } else if (event.key === 'Escape') {
      onEscape();
    }
  }

  searchInput.addEventListener('keydown', handleKeydown);

  return { reset };
}
