/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Polyfill: jsdom lacks scrollIntoView
Element.prototype.scrollIntoView ??= function () {};

const { attachDropdownKeyboard } = require('./dropdown_keyboard.js');

// ── Helpers ────────────────────────────────────────────────────

function keyDown(input, key) {
  const event = new KeyboardEvent('keydown', {
    key,
    bubbles: true,
    cancelable: true,
  });
  input.dispatchEvent(event);
  return event;
}

// ── Tests ──────────────────────────────────────────────────────

describe('attachDropdownKeyboard', () => {
  let searchInput, listContainer, dropdown, onSelect, onEscape, nav;

  function createItems(count) {
    listContainer.innerHTML = '';
    for (let i = 0; i < count; i++) {
      const item = document.createElement('div');
      item.dataset.value = `item-${i}`;
      item.textContent = `Item ${i}`;
      listContainer.appendChild(item);
    }
  }

  function getSelectableItems() {
    return listContainer.querySelectorAll('[data-value]');
  }

  function activeItem() {
    return listContainer.querySelector('.dropdown-active');
  }

  function press(key) {
    return keyDown(searchInput, key);
  }

  beforeEach(() => {
    dropdown = document.createElement('div');
    dropdown.className = 'link-dropdown';

    listContainer = document.createElement('div');
    dropdown.appendChild(listContainer);

    searchInput = document.createElement('input');
    dropdown.appendChild(searchInput);

    document.body.appendChild(dropdown);

    onSelect = vi.fn();
    onEscape = vi.fn();

    createItems(3);

    nav = attachDropdownKeyboard({
      searchInput,
      listContainer,
      getSelectableItems,
      onSelect,
      onEscape,
    });
  });

  afterEach(() => {
    if (nav) nav.destroy();
    document.body.innerHTML = '';
  });

  // ── Return value ──────────────────────────────────────────

  describe('return value', () => {
    it('returns an object with reset and destroy methods', () => {
      expect(typeof nav.reset).toBe('function');
      expect(typeof nav.destroy).toBe('function');
    });
  });

  // ── ArrowDown ─────────────────────────────────────────────

  describe('ArrowDown', () => {
    it('highlights the first item on first press', () => {
      press('ArrowDown');
      const items = getSelectableItems();
      expect(items[0].classList.contains('dropdown-active')).toBe(true);
    });

    it('advances to the next item on subsequent presses', () => {
      press('ArrowDown');
      press('ArrowDown');
      const items = getSelectableItems();
      expect(items[0].classList.contains('dropdown-active')).toBe(false);
      expect(items[1].classList.contains('dropdown-active')).toBe(true);
    });

    it('stops at the last item', () => {
      press('ArrowDown');
      press('ArrowDown');
      press('ArrowDown');
      press('ArrowDown'); // past the end
      const items = getSelectableItems();
      expect(items[2].classList.contains('dropdown-active')).toBe(true);
    });

    it('prevents default', () => {
      const event = press('ArrowDown');
      expect(event.defaultPrevented).toBe(true);
    });

    it('adds keyboard-navigating class to the dropdown', () => {
      press('ArrowDown');
      expect(dropdown.classList.contains('keyboard-navigating')).toBe(true);
    });

    it('scrolls the active item into view', () => {
      const items = getSelectableItems();
      const spy = vi.spyOn(items[0], 'scrollIntoView');
      press('ArrowDown');
      expect(spy).toHaveBeenCalledWith({ block: 'nearest' });
    });
  });

  // ── ArrowUp ───────────────────────────────────────────────

  describe('ArrowUp', () => {
    it('moves to the previous item', () => {
      press('ArrowDown');
      press('ArrowDown');
      press('ArrowUp');
      const items = getSelectableItems();
      expect(items[0].classList.contains('dropdown-active')).toBe(true);
      expect(items[1].classList.contains('dropdown-active')).toBe(false);
    });

    it('stops at the first item', () => {
      press('ArrowDown');
      press('ArrowUp');
      press('ArrowUp'); // past the start
      const items = getSelectableItems();
      expect(items[0].classList.contains('dropdown-active')).toBe(true);
    });

    it('highlights first item when pressed from initial state', () => {
      // activeIndex starts at -1; Math.max(-1 - 1, 0) = 0
      press('ArrowUp');
      const items = getSelectableItems();
      expect(items[0].classList.contains('dropdown-active')).toBe(true);
    });

    it('prevents default', () => {
      const event = press('ArrowUp');
      expect(event.defaultPrevented).toBe(true);
    });

    it('adds keyboard-navigating class to the dropdown', () => {
      press('ArrowUp');
      expect(dropdown.classList.contains('keyboard-navigating')).toBe(true);
    });
  });

  // ── Enter ─────────────────────────────────────────────────

  describe('Enter', () => {
    it('calls onSelect with the highlighted item', () => {
      press('ArrowDown');
      press('Enter');
      const items = getSelectableItems();
      expect(onSelect).toHaveBeenCalledWith(items[0]);
    });

    it('prevents default when an item is highlighted', () => {
      press('ArrowDown');
      const event = press('Enter');
      expect(event.defaultPrevented).toBe(true);
    });

    it('does not call onSelect when no item is highlighted', () => {
      press('Enter');
      expect(onSelect).not.toHaveBeenCalled();
    });

    // BUG REGRESSION: Enter with no highlighted item must still be captured
    // to prevent the parent form from submitting.
    it('prevents default even when no item is highlighted (prevents form submission)', () => {
      const event = press('Enter');
      expect(event.defaultPrevented).toBe(true);
    });
  });

  // ── Escape ────────────────────────────────────────────────

  describe('Escape', () => {
    it('calls onEscape when items exist', () => {
      press('Escape');
      expect(onEscape).toHaveBeenCalled();
    });

    it('calls onEscape when no items exist', () => {
      createItems(0);
      press('Escape');
      expect(onEscape).toHaveBeenCalled();
    });
  });

  // ── reset() ───────────────────────────────────────────────

  describe('reset', () => {
    it('clears the active highlight', () => {
      press('ArrowDown');
      expect(activeItem()).not.toBeNull();
      nav.reset();
      expect(activeItem()).toBeNull();
    });

    it('resets navigation so next ArrowDown starts from the top', () => {
      press('ArrowDown');
      press('ArrowDown'); // on item 1
      nav.reset();
      press('ArrowDown');
      const items = getSelectableItems();
      expect(items[0].classList.contains('dropdown-active')).toBe(true);
    });
  });

  // ── destroy() ─────────────────────────────────────────────

  describe('destroy', () => {
    it('removes the keydown listener so navigation stops', () => {
      nav.destroy();
      press('ArrowDown');
      expect(activeItem()).toBeNull();
    });

    it('stops calling onEscape after destroy', () => {
      nav.destroy();
      press('Escape');
      expect(onEscape).not.toHaveBeenCalled();
    });

    it('stops calling onSelect after destroy', () => {
      nav.destroy();
      press('ArrowDown');
      press('Enter');
      expect(onSelect).not.toHaveBeenCalled();
    });
  });

  // ── Empty items list ──────────────────────────────────────

  describe('empty items list', () => {
    beforeEach(() => {
      createItems(0);
    });

    it('ArrowDown does nothing', () => {
      expect(() => press('ArrowDown')).not.toThrow();
      expect(activeItem()).toBeNull();
    });

    it('ArrowUp does nothing', () => {
      expect(() => press('ArrowUp')).not.toThrow();
      expect(activeItem()).toBeNull();
    });

    it('Enter does not call onSelect', () => {
      press('Enter');
      expect(onSelect).not.toHaveBeenCalled();
    });

    // BUG REGRESSION: Enter with empty list must still be captured
    // to prevent the parent form from submitting.
    it('Enter prevents default even with no items (prevents form submission)', () => {
      const event = press('Enter');
      expect(event.defaultPrevented).toBe(true);
    });
  });

  // ── Active state styling ──────────────────────────────────

  describe('active state styling', () => {
    it('only one item has dropdown-active at a time', () => {
      press('ArrowDown');
      press('ArrowDown');
      const active = listContainer.querySelectorAll('.dropdown-active');
      expect(active.length).toBe(1);
    });

    it('non-arrow keys do not add keyboard-navigating class', () => {
      press('Enter');
      expect(dropdown.classList.contains('keyboard-navigating')).toBe(false);
    });
  });

  // ── Dynamic items ─────────────────────────────────────────

  describe('dynamic items', () => {
    it('re-queries items on each keydown', () => {
      press('ArrowDown'); // on item 0
      // Replace items (simulating re-render)
      createItems(5);
      press('ArrowDown'); // should go to item 1 of the new list
      const items = getSelectableItems();
      expect(items[1].classList.contains('dropdown-active')).toBe(true);
    });
  });
});
