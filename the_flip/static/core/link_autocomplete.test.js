/**
 * @vitest-environment jsdom
 */
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Polyfills for jsdom ──────────────────────────────────────

Element.prototype.scrollIntoView ??= function () {};

// jsdom doesn't implement execCommand — define a default that returns false
// (matching the "unsupported" behavior). Tests can spy/mock on this.
document.execCommand ??= () => false;

// ── Mocks (must be defined before module import) ────────────

let capturedKeyboardOptions = null;

global.attachDropdownKeyboard = vi.fn((options) => {
  capturedKeyboardOptions = options;
  return { destroy: vi.fn(), reset: vi.fn() };
});

// ── Module under test ───────────────────────────────────────

const { initLinkAutocomplete, _resetCache } = await import('./link_autocomplete.js');

// ── Test Data ───────────────────────────────────────────────

const MOCK_TYPES = [
  { name: 'page', label: 'Wiki Page', description: 'Link to a wiki page' },
  { name: 'machine', label: 'Machine', description: 'Link to a machine' },
];

const MOCK_RESULTS = [
  { ref: 'getting-started', label: 'Getting Started', path: '' },
  { ref: 'troubleshooting', label: 'Troubleshooting', path: 'guides' },
];

// ── Helpers ─────────────────────────────────────────────────

function setupFetchMock(overrides = {}) {
  const types = overrides.types ?? MOCK_TYPES;
  const results = overrides.results ?? MOCK_RESULTS;
  const totalCount = overrides.totalCount ?? results.length;

  global.fetch = vi.fn((url) => {
    if (url.includes('/api/link-types/')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ types }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ results, total_count: totalCount }),
    });
  });
}

function createTextarea(value = '') {
  const textarea = document.createElement('textarea');
  textarea.setAttribute('data-link-autocomplete', '');
  textarea.setAttribute('data-link-api-url', '/api/link-targets/');
  textarea.value = value;
  textarea.selectionStart = textarea.selectionEnd = value.length;
  document.body.appendChild(textarea);
  return textarea;
}

/** Simulate typing text at the current cursor position. */
function typeText(textarea, text) {
  const pos = textarea.selectionStart;
  const before = textarea.value.substring(0, pos);
  const after = textarea.value.substring(pos);
  textarea.value = before + text + after;
  textarea.selectionStart = textarea.selectionEnd = pos + text.length;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
}

function keyDown(element, key, options = {}) {
  const event = new KeyboardEvent('keydown', {
    key,
    bubbles: true,
    cancelable: true,
    ...options,
  });
  element.dispatchEvent(event);
  return event;
}

/** Get the DOM elements created by initLinkAutocomplete. */
function getElements(textarea) {
  const wrapper = textarea.parentElement;
  const dropdown = wrapper.querySelector('.link-dropdown');
  const typeList = dropdown.querySelector('[data-type-list]');
  const searchStage = dropdown.querySelector('[data-search-stage]');
  const searchInput = dropdown.querySelector('.link-dropdown__search');
  const resultsList = dropdown.querySelector('[data-results-list]');
  return { wrapper, dropdown, typeList, searchStage, searchInput, resultsList };
}

/** Type [[ and wait for type selection to render. */
async function openTypes(textarea) {
  typeText(textarea, '[[');
  await vi.advanceTimersByTimeAsync(0);
  return getElements(textarea);
}

/** Open types, press ArrowDown + Enter to select first type, wait for results. */
async function openSearch(textarea) {
  const els = await openTypes(textarea);
  keyDown(textarea, 'ArrowDown');
  keyDown(textarea, 'Enter');
  await vi.advanceTimersByTimeAsync(0);
  return els;
}

/** Full flow: open types → select type → click first result. */
async function insertFirstResult(textarea) {
  const els = await openSearch(textarea);
  const firstResult = els.resultsList.querySelector('[data-item]');
  firstResult.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
  return els;
}

// ── Tests ───────────────────────────────────────────────────

describe('link_autocomplete', () => {
  let textarea;

  beforeEach(() => {
    vi.useFakeTimers();
    _resetCache();
    capturedKeyboardOptions = null;
    global.attachDropdownKeyboard.mockClear();
    setupFetchMock();
    textarea = createTextarea();
    initLinkAutocomplete(textarea);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    document.body.innerHTML = '';
  });

  // ── Initialization ──────────────────────────────────────

  describe('initialization', () => {
    test('wraps textarea in autocomplete wrapper', () => {
      const wrapper = textarea.parentElement;
      expect(wrapper.className).toBe('link-autocomplete-wrapper');
    });

    test('creates dropdown and mirror elements', () => {
      const { dropdown } = getElements(textarea);
      expect(dropdown).not.toBeNull();
      expect(dropdown.classList.contains('hidden')).toBe(true);

      const mirror = textarea.parentElement.querySelector('.link-mirror');
      expect(mirror).not.toBeNull();
      expect(mirror.getAttribute('aria-hidden')).toBe('true');
    });

    test('skips textarea without data-link-api-url', () => {
      const bare = document.createElement('textarea');
      bare.setAttribute('data-link-autocomplete', '');
      // No data-link-api-url
      document.body.appendChild(bare);

      initLinkAutocomplete(bare);

      // Should not be wrapped
      expect(bare.parentElement).toBe(document.body);
    });

    test('prefetches link types on init', () => {
      expect(global.fetch).toHaveBeenCalledWith('/api/link-types/');
    });

    test('caches types across multiple calls', async () => {
      // First call already happened in init. Open autocomplete to trigger
      // showTypeSelection which calls fetchLinkTypes again.
      await openTypes(textarea);

      // fetch was called once for the prefetch — showTypeSelection reuses cache
      const typesCalls = global.fetch.mock.calls.filter((c) => c[0].includes('/api/link-types/'));
      expect(typesCalls).toHaveLength(1);
    });
  });

  // ── Trigger Detection ───────────────────────────────────

  describe('trigger detection', () => {
    test('[[ opens type selection dropdown', async () => {
      const { dropdown, typeList } = await openTypes(textarea);

      expect(dropdown.classList.contains('hidden')).toBe(false);
      expect(typeList.querySelectorAll('[data-type]')).toHaveLength(2);
    });

    test('single [ does not trigger', () => {
      typeText(textarea, '[');
      const { dropdown } = getElements(textarea);
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });

    test('[[ after existing text triggers at correct position', async () => {
      textarea.value = 'See also: ';
      textarea.selectionStart = textarea.selectionEnd = 10;

      const { dropdown } = await openTypes(textarea);
      expect(dropdown.classList.contains('hidden')).toBe(false);
    });
  });

  // ── Type Selection ──────────────────────────────────────

  describe('type selection', () => {
    test('displays all fetched link types with labels', async () => {
      const { typeList } = await openTypes(textarea);
      const items = typeList.querySelectorAll('[data-type]');

      expect(items).toHaveLength(2);
      expect(items[0].dataset.type).toBe('page');
      expect(items[0].textContent).toContain('Wiki Page');
      expect(items[1].dataset.type).toBe('machine');
    });

    test('ArrowDown/ArrowUp navigates type items', async () => {
      const { typeList } = await openTypes(textarea);
      const items = typeList.querySelectorAll('[data-type]');

      keyDown(textarea, 'ArrowDown');
      expect(items[0].classList.contains('dropdown-active')).toBe(true);
      expect(items[1].classList.contains('dropdown-active')).toBe(false);

      keyDown(textarea, 'ArrowDown');
      expect(items[0].classList.contains('dropdown-active')).toBe(false);
      expect(items[1].classList.contains('dropdown-active')).toBe(true);

      keyDown(textarea, 'ArrowUp');
      expect(items[0].classList.contains('dropdown-active')).toBe(true);
      expect(items[1].classList.contains('dropdown-active')).toBe(false);
    });

    test('Enter on highlighted type opens search stage', async () => {
      const { searchStage } = await openTypes(textarea);

      keyDown(textarea, 'ArrowDown');
      keyDown(textarea, 'Enter');
      await vi.advanceTimersByTimeAsync(0);

      expect(searchStage.classList.contains('hidden')).toBe(false);
      expect(global.attachDropdownKeyboard).toHaveBeenCalled();
    });

    test('mouse click on type opens search stage', async () => {
      const { typeList, searchStage } = await openTypes(textarea);
      const firstType = typeList.querySelector('[data-type]');

      firstType.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
      await vi.advanceTimersByTimeAsync(0);

      expect(searchStage.classList.contains('hidden')).toBe(false);
    });

    test('Escape closes dropdown', async () => {
      const { dropdown } = await openTypes(textarea);
      expect(dropdown.classList.contains('hidden')).toBe(false);

      keyDown(textarea, 'Escape');
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });

    test('ArrowLeft closes dropdown', async () => {
      const { dropdown } = await openTypes(textarea);

      keyDown(textarea, 'ArrowLeft');
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });
  });

  // ── Search Stage ────────────────────────────────────────

  describe('search', () => {
    test('search input placeholder includes type label', async () => {
      const { searchInput } = await openSearch(textarea);
      expect(searchInput.placeholder).toBe('Search wiki page...');
    });

    test('initial results load without debounce', async () => {
      await openSearch(textarea);

      // fetch for search should have been called with empty query
      const searchCalls = global.fetch.mock.calls.filter((c) => !c[0].includes('/api/link-types/'));
      expect(searchCalls).toHaveLength(1);
      expect(searchCalls[0][0]).toContain('type=page');
      expect(searchCalls[0][0]).toContain('q=');
    });

    test('displays results with labels', async () => {
      const { resultsList } = await openSearch(textarea);
      const items = resultsList.querySelectorAll('[data-item]');

      expect(items).toHaveLength(2);
      expect(items[0].dataset.ref).toBe('getting-started');
      expect(items[0].textContent).toContain('Getting Started');
    });

    test('displays path when present', async () => {
      const { resultsList } = await openSearch(textarea);
      const secondItem = resultsList.querySelectorAll('[data-item]')[1];

      expect(secondItem.textContent).toContain('guides/');
    });

    test('empty results show "No results found"', async () => {
      setupFetchMock({ results: [] });
      _resetCache();

      const els = await openSearch(textarea);
      const empty = els.resultsList.querySelector('.link-dropdown__empty');
      expect(empty.textContent).toBe('No results found');
    });

    test('shows count hint when more results exist', async () => {
      setupFetchMock({ totalCount: 50 });

      // Need fresh init after changing mock
      document.body.innerHTML = '';
      _resetCache();
      textarea = createTextarea();
      initLinkAutocomplete(textarea);

      const { resultsList } = await openSearch(textarea);
      const hint = resultsList.querySelector('.link-dropdown__hint');
      expect(hint.textContent).toContain('Showing 2 of 50');
    });

    test('typing in search triggers debounced fetch', async () => {
      const { searchInput } = await openSearch(textarea);

      // Clear previous fetch calls
      global.fetch.mockClear();

      searchInput.value = 'test';
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));

      // Not called yet (debounced)
      const searchCallsBefore = global.fetch.mock.calls.filter(
        (c) => !c[0].includes('/api/link-types/')
      );
      expect(searchCallsBefore).toHaveLength(0);

      // Advance past debounce delay
      await vi.advanceTimersByTimeAsync(300);

      const searchCallsAfter = global.fetch.mock.calls.filter(
        (c) => !c[0].includes('/api/link-types/')
      );
      expect(searchCallsAfter).toHaveLength(1);
      expect(searchCallsAfter[0][0]).toContain('q=test');
    });

    test('Backspace on empty search returns to type selection', async () => {
      const { typeList, searchInput, searchStage } = await openSearch(textarea);

      expect(searchStage.classList.contains('hidden')).toBe(false);

      keyDown(searchInput, 'Backspace');

      // Should be back on type stage
      await vi.advanceTimersByTimeAsync(0);
      expect(typeList.classList.contains('hidden')).toBe(false);
      expect(searchStage.classList.contains('hidden')).toBe(true);
    });

    test('going back from search preserves the highlighted type', async () => {
      const { typeList, searchInput } = await openTypes(textarea);

      // Navigate to second type (Machine) and select it
      keyDown(textarea, 'ArrowDown');
      keyDown(textarea, 'ArrowDown');
      keyDown(textarea, 'Enter');
      await vi.advanceTimersByTimeAsync(0);

      // Go back via Backspace on empty search
      keyDown(searchInput, 'Backspace');
      await vi.advanceTimersByTimeAsync(0);

      // Second type should still be highlighted
      const items = typeList.querySelectorAll('[data-type]');
      expect(items[1].classList.contains('dropdown-active')).toBe(true);
      expect(items[0].classList.contains('dropdown-active')).toBe(false);
    });

    test('ArrowLeft at cursor start returns to type selection', async () => {
      const { typeList, searchInput, searchStage } = await openSearch(textarea);

      searchInput.selectionStart = 0;
      keyDown(searchInput, 'ArrowLeft');

      await vi.advanceTimersByTimeAsync(0);
      expect(typeList.classList.contains('hidden')).toBe(false);
      expect(searchStage.classList.contains('hidden')).toBe(true);
    });

    test('keyboard nav is set up for search results', async () => {
      await openSearch(textarea);

      expect(capturedKeyboardOptions).not.toBeNull();
      expect(capturedKeyboardOptions.onEscape).toBeInstanceOf(Function);
      expect(capturedKeyboardOptions.onSelect).toBeInstanceOf(Function);
    });
  });

  // ── Link Insertion ──────────────────────────────────────

  describe('link insertion', () => {
    test('inserts [[type:ref]] at trigger position', async () => {
      await insertFirstResult(textarea);
      expect(textarea.value).toBe('[[page:getting-started]]');
    });

    test('preserves text before and after the trigger', async () => {
      textarea.value = 'See also: ';
      textarea.selectionStart = textarea.selectionEnd = 10;

      await insertFirstResult(textarea);
      expect(textarea.value).toBe('See also: [[page:getting-started]]');
    });

    test('preserves text after cursor when trigger is mid-text', async () => {
      textarea.value = 'Link:  and more text';
      textarea.selectionStart = textarea.selectionEnd = 6;

      // Type [[ at cursor (position 6)
      const { resultsList } = await openSearch(textarea);
      const firstResult = resultsList.querySelector('[data-item]');
      firstResult.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));

      expect(textarea.value).toBe('Link: [[page:getting-started]] and more text');
    });

    test('positions cursor after inserted link', async () => {
      await insertFirstResult(textarea);

      const expectedPos = '[[page:getting-started]]'.length;
      expect(textarea.selectionStart).toBe(expectedPos);
      expect(textarea.selectionEnd).toBe(expectedPos);
    });

    test('closes dropdown after insertion', async () => {
      const { dropdown } = await insertFirstResult(textarea);
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });

    test('dispatches input event after insertion', async () => {
      const inputSpy = vi.fn();
      textarea.addEventListener('input', inputSpy);

      await insertFirstResult(textarea);

      // At least one input event from the insertion (typeText also fires input)
      const callCount = inputSpy.mock.calls.length;
      expect(callCount).toBeGreaterThanOrEqual(2); // typeText [[ + insertion
    });

    test('keyboard selection via onSelect callback works', async () => {
      const { resultsList } = await openSearch(textarea);

      // Simulate keyboard selection through the captured callback
      const firstResult = resultsList.querySelector('[data-item]');
      capturedKeyboardOptions.onSelect(firstResult);

      expect(textarea.value).toBe('[[page:getting-started]]');
    });

    test('onSelect with invalid item closes dropdown', async () => {
      const { dropdown } = await openSearch(textarea);

      capturedKeyboardOptions.onSelect(null);
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });
  });

  // ── Close Behavior ──────────────────────────────────────

  describe('close behavior', () => {
    test('click on textarea closes dropdown', async () => {
      const { dropdown } = await openTypes(textarea);
      expect(dropdown.classList.contains('hidden')).toBe(false);

      textarea.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });

    test('outside click closes dropdown', async () => {
      const { dropdown } = await openTypes(textarea);

      document.body.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });

    test('Backspace past trigger in type stage closes dropdown', async () => {
      const { dropdown } = await openTypes(textarea);

      // Cursor is at position 2 (after [[), triggerStart is 0
      // Backspace would move cursor to 1, which is <= triggerStart + 2
      textarea.selectionStart = textarea.selectionEnd = 1;
      keyDown(textarea, 'Backspace');

      expect(dropdown.classList.contains('hidden')).toBe(true);
    });

    test('Escape callback from keyboard nav closes dropdown', async () => {
      const { dropdown } = await openSearch(textarea);

      capturedKeyboardOptions.onEscape();
      expect(dropdown.classList.contains('hidden')).toBe(true);
    });
  });

  // ── Undo-Safe Editing ─────────────────────────────────

  describe('undo-safe editing', () => {
    test('uses execCommand for link insertion', async () => {
      const execSpy = vi.spyOn(document, 'execCommand');

      await insertFirstResult(textarea);

      expect(execSpy).toHaveBeenCalledWith('insertText', false, '[[page:getting-started]]');
      execSpy.mockRestore();
    });

    test('sets selection to replacement range before execCommand', async () => {
      const selections = [];
      const execSpy = vi.spyOn(document, 'execCommand').mockImplementation(() => {
        // Capture the selection state at the moment execCommand is called
        selections.push({
          start: textarea.selectionStart,
          end: textarea.selectionEnd,
        });
        return false; // Let fallback handle the actual value change
      });

      await insertFirstResult(textarea);

      // execCommand should have been called with selection covering the [[ trigger
      expect(selections).toHaveLength(1);
      expect(selections[0].start).toBe(0); // triggerStart
      expect(selections[0].end).toBe(2); // cursor was after [[
      execSpy.mockRestore();
    });

    test('focuses textarea before execCommand (focus may be on search input)', async () => {
      const focusedElements = [];
      const execSpy = vi.spyOn(document, 'execCommand').mockImplementation(() => {
        focusedElements.push(document.activeElement);
        return false;
      });

      await insertFirstResult(textarea);

      expect(focusedElements).toHaveLength(1);
      expect(focusedElements[0]).toBe(textarea);
      execSpy.mockRestore();
    });

    test('falls back to value assignment when execCommand fails', async () => {
      // jsdom's execCommand returns false by default — fallback runs
      await insertFirstResult(textarea);

      expect(textarea.value).toBe('[[page:getting-started]]');
      expect(textarea.selectionStart).toBe(24);
    });
  });
});
