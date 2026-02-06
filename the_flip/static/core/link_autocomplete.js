/**
 * Link Autocomplete
 *
 * Inline autocomplete for inserting [[type:ref]] links when typing [[ in textareas.
 * Link types are fetched from the server — JS has zero knowledge of type semantics.
 *
 * Two-stage flow:
 * 1. Type [[ -> Show type selection (fetched from /api/link-types/)
 * 2. Select type -> Show search results for that type
 *
 * Requires: dropdown_keyboard.js (for keyboard navigation)
 *
 * Usage:
 *   <textarea data-link-autocomplete data-link-api-url="/api/link-targets/">
 *   </textarea>
 */

(function () {
  'use strict';

  // Debounce delay for API searches
  const DEBOUNCE_MS = 300;

  // Types endpoint — prefetched once per page load
  const TYPES_URL = '/api/link-types/';

  // Shared cache: fetched once, reused by all textarea instances on the page
  let linkTypesCache = null;
  let linkTypesFetching = null;

  function fetchLinkTypes() {
    if (linkTypesCache) return Promise.resolve(linkTypesCache);
    if (linkTypesFetching) return linkTypesFetching;

    linkTypesFetching = fetch(TYPES_URL)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => {
        linkTypesCache = data.types || [];
        linkTypesFetching = null;
        return linkTypesCache;
      })
      .catch(() => {
        linkTypesFetching = null;
        return [];
      });

    return linkTypesFetching;
  }

  function initLinkAutocomplete(textarea) {
    const apiUrl = textarea.dataset.linkApiUrl;
    if (!apiUrl) return;

    // Prefetch types immediately — by the time user types [[, data is ready
    fetchLinkTypes();

    // State
    let isOpen = false;
    let stage = 'type'; // 'type' or 'search'
    let selectedType = null;
    let selectedLabel = null;
    let triggerStart = -1; // Position where [[ was typed
    let debounceTimer = null;
    let keyboardNav = null;
    let typeActiveIndex = -1; // Track type selection separately

    // Create dropdown container
    const dropdown = document.createElement('div');
    dropdown.className = 'link-dropdown hidden';
    dropdown.innerHTML = `
      <div data-type-list></div>
      <div data-search-stage class="hidden">
        <input type="text" class="link-dropdown__search" placeholder="Search...">
        <div data-results-list class="link-dropdown__results"></div>
      </div>
    `;

    // Position dropdown relative to textarea's parent (not body) for proper containment
    const wrapper = document.createElement('div');
    wrapper.className = 'link-autocomplete-wrapper';
    wrapper.style.position = 'relative';
    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.appendChild(textarea);
    wrapper.appendChild(dropdown);

    // Remove keyboard-navigating class on mouse movement so :hover works again
    dropdown.addEventListener('mousemove', () => {
      dropdown.classList.remove('keyboard-navigating');
    });

    const typeList = dropdown.querySelector('[data-type-list]');
    const searchStage = dropdown.querySelector('[data-search-stage]');
    const searchInput = dropdown.querySelector('.link-dropdown__search');
    const resultsList = dropdown.querySelector('[data-results-list]');

    // Mirror div for cursor position calculation
    const mirror = document.createElement('div');
    mirror.className = 'link-mirror';
    mirror.setAttribute('aria-hidden', 'true');
    wrapper.appendChild(mirror);

    function getTextareaStyles() {
      const computed = window.getComputedStyle(textarea);
      return {
        fontFamily: computed.fontFamily,
        fontSize: computed.fontSize,
        fontWeight: computed.fontWeight,
        lineHeight: computed.lineHeight,
        padding: computed.padding,
        border: computed.border,
        boxSizing: computed.boxSizing,
        whiteSpace: 'pre-wrap',
        wordWrap: 'break-word',
        width: textarea.offsetWidth + 'px',
      };
    }

    function updateMirrorStyles() {
      const styles = getTextareaStyles();
      Object.assign(mirror.style, styles);
      mirror.style.position = 'absolute';
      mirror.style.top = '0';
      mirror.style.left = '0';
      mirror.style.visibility = 'hidden';
      mirror.style.pointerEvents = 'none';
      mirror.style.overflow = 'hidden';
      mirror.style.height = 'auto';
    }

    function getCursorPosition() {
      updateMirrorStyles();

      const text = textarea.value.substring(0, textarea.selectionStart);
      // Escape HTML and add marker span
      const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
      mirror.innerHTML = escaped + '<span data-cursor></span>';

      const cursorSpan = mirror.querySelector('[data-cursor]');
      const cursorRect = cursorSpan.getBoundingClientRect();
      const textareaRect = textarea.getBoundingClientRect();

      // Calculate position relative to textarea
      let left = cursorRect.left - textareaRect.left + textarea.scrollLeft;
      let top = cursorRect.top - textareaRect.top - textarea.scrollTop + cursorSpan.offsetHeight;

      // Adjust for scroll position within textarea
      top = Math.min(top, textarea.offsetHeight - 20);

      return { left, top };
    }

    function positionDropdown() {
      const pos = getCursorPosition();
      dropdown.style.left = pos.left + 'px';
      dropdown.style.top = pos.top + 'px';
    }

    function showTypeSelection() {
      fetchLinkTypes().then((types) => {
        if (!isOpen) return; // User may have closed while waiting

        stage = 'type';
        typeActiveIndex = -1;
        typeList.innerHTML = '';
        typeList.classList.remove('hidden');
        searchStage.classList.add('hidden');

        types.forEach((linkType) => {
          const item = document.createElement('div');
          item.className = 'link-dropdown__item';
          item.dataset.type = linkType.name;
          item.innerHTML = `
            <span class="link-dropdown__item-label">${escapeHtml(linkType.label)}</span>
            <span class="link-dropdown__item-desc">${escapeHtml(linkType.description)}</span>
          `;
          item.addEventListener('mousedown', (e) => {
            e.preventDefault();
            selectType(linkType.name, linkType.label);
          });
          typeList.appendChild(item);
        });

        dropdown.classList.remove('hidden');
        positionDropdown();
      });
    }

    function updateTypeActiveState() {
      const items = typeList.querySelectorAll('[data-type]');
      items.forEach((item, index) => {
        if (index === typeActiveIndex) {
          item.classList.add('dropdown-active');
          item.scrollIntoView({ block: 'nearest' });
        } else {
          item.classList.remove('dropdown-active');
        }
      });
    }

    function selectType(type, label) {
      // Destroy previous keyboard nav to avoid stacking event listeners
      if (keyboardNav) {
        keyboardNav.destroy();
        keyboardNav = null;
      }

      selectedType = type;
      selectedLabel = label || type;
      stage = 'search';
      typeActiveIndex = -1;
      typeList.classList.add('hidden');
      searchStage.classList.remove('hidden');
      searchInput.value = '';
      resultsList.innerHTML = '';

      searchInput.placeholder = `Search ${selectedLabel.toLowerCase()}...`;

      searchInput.focus();

      // Load initial results (empty query)
      fetchResults('');

      // Set up keyboard navigation for search results only
      keyboardNav = attachDropdownKeyboard({
        searchInput: searchInput,
        listContainer: resultsList,
        getSelectableItems: () => resultsList.querySelectorAll('[data-item]'),
        onSelect: handleResultSelect,
        onEscape: closeDropdown,
      });
    }

    function fetchResults(query) {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }

      debounceTimer = setTimeout(
        () => {
          const url = `${apiUrl}?type=${selectedType}&q=${encodeURIComponent(query)}`;
          fetch(url)
            .then((response) => (response.ok ? response.json() : Promise.reject()))
            .then((data) => renderResults(data.results || []))
            .catch(() => renderResults([]));
        },
        query ? DEBOUNCE_MS : 0
      ); // Immediate for empty query
    }

    function renderResults(results) {
      resultsList.innerHTML = '';

      if (results.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'link-dropdown__empty';
        empty.textContent = 'No results found';
        resultsList.appendChild(empty);
        return;
      }

      results.forEach((result) => {
        const item = document.createElement('div');
        item.className = 'link-dropdown__item';
        item.dataset.item = 'true';
        item.dataset.ref = result.ref;

        const pathHtml = result.path
          ? `<span class="link-dropdown__item-path">${escapeHtml(result.path)}/</span>`
          : '';
        item.innerHTML = `
          <span class="link-dropdown__item-label">${escapeHtml(result.label)}</span>
          ${pathHtml}
        `;

        item.addEventListener('mousedown', (e) => {
          e.preventDefault();
          handleResultSelect(item);
        });

        resultsList.appendChild(item);
      });

      if (keyboardNav) {
        keyboardNav.reset();
      }
    }

    function handleResultSelect(item) {
      if (!item || !item.dataset || !item.dataset.ref) {
        closeDropdown();
        return;
      }

      // Guard against stale state (e.g., if closeDropdown() already ran)
      if (!selectedType || triggerStart < 0) {
        closeDropdown();
        return;
      }

      insertLink(`[[${selectedType}:${item.dataset.ref}]]`);
    }

    function insertLink(linkText) {
      // Replace the [[ trigger with the full link
      const before = textarea.value.substring(0, triggerStart);
      const after = textarea.value.substring(textarea.selectionStart);
      textarea.value = before + linkText + after;

      // Position cursor after the inserted link
      const newPosition = triggerStart + linkText.length;
      textarea.setSelectionRange(newPosition, newPosition);

      closeDropdown();
      textarea.focus();

      // Trigger input event for any other listeners
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function closeDropdown() {
      isOpen = false;
      stage = 'type';
      selectedType = null;
      selectedLabel = null;
      triggerStart = -1;
      typeActiveIndex = -1;
      if (keyboardNav) {
        keyboardNav.destroy();
        keyboardNav = null;
      }
      dropdown.classList.add('hidden');

      if (debounceTimer) {
        clearTimeout(debounceTimer);
        debounceTimer = null;
      }
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    // Detect [[ trigger
    function checkForTrigger() {
      const pos = textarea.selectionStart;
      const text = textarea.value;

      // Check if the last two characters are [[
      if (pos >= 2 && text.substring(pos - 2, pos) === '[[') {
        triggerStart = pos - 2;
        isOpen = true;
        showTypeSelection();
      }
    }

    // Event listeners
    textarea.addEventListener('input', () => {
      if (!isOpen) {
        checkForTrigger();
      }
    });

    textarea.addEventListener('keydown', (e) => {
      if (!isOpen) return;

      // When in type selection stage, handle keyboard on textarea directly
      if (stage === 'type') {
        const typeItems = typeList.querySelectorAll('[data-type]');
        const itemCount = typeItems.length;

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          dropdown.classList.add('keyboard-navigating');
          typeActiveIndex = Math.min(typeActiveIndex + 1, itemCount - 1);
          updateTypeActiveState();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          dropdown.classList.add('keyboard-navigating');
          typeActiveIndex = Math.max(typeActiveIndex - 1, 0);
          updateTypeActiveState();
        } else if (e.key === 'Enter' || e.key === 'ArrowRight') {
          e.preventDefault();
          if (typeActiveIndex >= 0 && typeActiveIndex < itemCount) {
            const activeItem = typeItems[typeActiveIndex];
            // Find label from the cached types
            const typeName = activeItem.dataset.type;
            const typeInfo = (linkTypesCache || []).find((t) => t.name === typeName);
            selectType(typeName, typeInfo?.label);
          }
        } else if (e.key === 'Escape' || e.key === 'ArrowLeft') {
          e.preventDefault();
          closeDropdown();
        } else if (e.key === 'Backspace') {
          // Check if we're deleting past the trigger
          const pos = textarea.selectionStart;
          if (pos <= triggerStart + 2) {
            closeDropdown();
          }
        }
      }
    });

    searchInput.addEventListener('input', () => {
      fetchResults(searchInput.value);
    });

    function goBackToTypeSelection() {
      showTypeSelection();
      textarea.focus();
      // Reset cursor to after [[
      textarea.setSelectionRange(triggerStart + 2, triggerStart + 2);
    }

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Backspace' && !searchInput.value) {
        e.preventDefault();
        goBackToTypeSelection();
      } else if (e.key === 'ArrowLeft' && searchInput.selectionStart === 0) {
        e.preventDefault();
        goBackToTypeSelection();
      }
    });

    // Close when clicking the textarea itself (e.g., user clicks away from dropdown)
    textarea.addEventListener('click', () => {
      if (isOpen) {
        closeDropdown();
      }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (isOpen && !wrapper.contains(e.target)) {
        closeDropdown();
      }
    });

    // Close on blur (after small delay to allow click events)
    textarea.addEventListener('blur', () => {
      if (isOpen && stage === 'type') {
        setTimeout(() => {
          if (!searchInput.matches(':focus')) {
            closeDropdown();
          }
        }, 150);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const textareas = document.querySelectorAll('[data-link-autocomplete]');
    textareas.forEach((textarea) => initLinkAutocomplete(textarea));
  });
})();
