/**
 * Checkbox Toggle Module
 *
 * Enables interactive task list checkboxes in [data-text-card] containers.
 * Checkboxes rendered outside data-text-card remain disabled (read-only).
 *
 * Auto-initializes on elements with [data-text-card] attribute.
 *
 * Behavior:
 * 1. Finds all checkboxes with [data-checkbox-index] inside [data-text-card]
 * 2. Removes their "disabled" attribute to make them interactive
 * 3. On click: toggles the Nth checkbox marker in the raw markdown textarea
 * 4. POSTs the updated text via the existing update_text action
 * 5. On failure: reverts the checkbox and shows error status
 * 6. Enter key in textarea auto-continues task lists (like GitHub)
 *    - Creates new unchecked item with same indentation
 *    - Splits text if cursor is mid-line
 *    - Removes prefix if line is empty
 *
 * Limitation: 4-space indented code blocks are not detected. Task markers
 * inside indented code blocks will cause index mismatch with rendered
 * checkboxes. Use fenced code blocks (``` or ~~~) instead.  We decided that
 * supporting this is too complex given that indented code blocks are no
 * longer commonly used.
 */
(function () {
  'use strict';

  function getCsrfToken() {
    const cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : '';
  }

  /**
   * Handle Enter key in textarea to auto-continue task lists.
   *
   * When pressing Enter on a task list line:
   * - Creates a new unchecked task item with same indentation
   * - Splits text if cursor is in middle of content
   * - Removes the task prefix if line is empty (just "- [ ] ")
   * - Preserves blockquote prefixes ("> ")
   *
   * @param {HTMLTextAreaElement} textarea - The textarea element
   */
  function initTaskListEnter(textarea) {
    textarea.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;

      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const value = textarea.value;

      // Don't interfere if there's a selection
      if (start !== end) return;

      // Find the current line boundaries
      const lineStart = value.lastIndexOf('\n', start - 1) + 1;
      let lineEnd = value.indexOf('\n', start);
      if (lineEnd === -1) lineEnd = value.length;

      // Get text before and after cursor on this line
      const beforeCursor = value.substring(lineStart, start);
      const afterCursor = value.substring(start, lineEnd);

      // Match task list pattern: optional blockquote, optional indent, list marker, checkbox
      // Groups: 1=blockquote+indent prefix, 2=list marker (-, *, +, or number.), 3=content before cursor
      // Checkbox content: spaces (including none) or x/X - matches [], [ ], [  ], [x], [X]
      const match = beforeCursor.match(/^((?:>\s*)*\s*)([-*+]|\d+\.) \[(?: *|[xX])\] ?(.*)$/);
      if (!match) return; // Not a task list line, let default behavior happen

      const prefix = match[1]; // Blockquote and/or indent
      const marker = match[2]; // List marker
      const contentBeforeCursor = match[3];

      // If the line is empty (just checkbox with no content) and nothing after cursor
      if (contentBeforeCursor.trim() === '' && afterCursor.trim() === '') {
        e.preventDefault();
        // Remove the task prefix, keep just the blockquote/indent prefix
        const before = value.substring(0, lineStart);
        const after = value.substring(lineEnd);
        textarea.value = before + prefix + after;
        textarea.selectionStart = textarea.selectionEnd = lineStart + prefix.length;
        // Trigger input event for any listeners
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        return;
      }

      e.preventDefault();

      // For numbered lists, increment the number
      let newMarker = marker;
      if (/^\d+\.$/.test(marker)) {
        newMarker = `${parseInt(marker) + 1}.`;
      }

      // Build new line: newline + prefix + marker + unchecked checkbox + text after cursor
      const newLine = `\n${prefix}${newMarker} [ ] ${afterCursor}`;

      // Insert new line at cursor, removing text after cursor from current line
      const newValue = value.substring(0, start) + newLine + value.substring(lineEnd);
      textarea.value = newValue;

      // Position cursor after the new checkbox (before any moved text)
      const cursorPos = start + `\n${prefix}${newMarker} [ ] `.length;
      textarea.selectionStart = textarea.selectionEnd = cursorPos;

      // Trigger input event for any listeners
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  /**
   * Toggle the Nth task list marker in raw markdown text.
   *
   * Finds the Nth occurrence of list item checkbox markers and toggles
   * between checked/unchecked. Supports all markdown list types:
   * - Unordered: "- [ ]", "* [ ]", "+ [ ]"
   * - Ordered: "1. [ ]", "2. [ ]", etc.
   * - Inside blockquotes: "> - [ ]"
   *
   * Skips markers inside fenced code blocks (``` or ~~~).
   * Note: 4-space indented code blocks are NOT detected - use fenced blocks.
   *
   * @param {string} text - Raw markdown text
   * @param {number} index - Zero-based checkbox index
   * @returns {string} Updated markdown text
   */
  function toggleCheckboxInMarkdown(text, index) {
    // Split text into segments: outside code blocks vs inside
    // Code blocks start and end with ``` or ~~~ on their own line
    const segments = text.split(/^((?:```|~~~)[\s\S]*?^(?:```|~~~))/gm);
    let count = 0;
    // Match task list markers for all list types: -, *, +, or numbered (1., 2., etc.)
    // Also handles blockquote prefixes (> ) which can appear before the list marker
    const pattern = /^((?:>\s*)*\s*(?:[-*+]|\d+\.) )\[( *|[xX])\]/gm;

    const result = segments.map((segment, i) => {
      // Odd indices are inside code blocks (captured groups)
      if (i % 2 === 1) {
        return segment;
      }

      // Process segments outside code blocks
      return segment.replace(pattern, (match, prefix, checkChar) => {
        if (count++ !== index) {
          return match;
        }
        // Toggle: empty or spaces -> x, x/X -> single space
        const newChar = checkChar.trim() === '' ? 'x' : ' ';
        return `${prefix}[${newChar}]`;
      });
    });

    return result.join('');
  }

  function initTextCard(card) {
    const textarea = card.querySelector('[data-text-textarea]');
    if (!textarea) {
      console.error('[checkbox_toggle] No textarea found in card:', card);
      return;
    }

    // Initialize Enter key handler for task list continuation
    initTaskListEnter(textarea);

    const checkboxes = card.querySelectorAll('input[data-checkbox-index]');
    if (checkboxes.length === 0) return;

    // Enable checkboxes (they render disabled by default for list views)
    checkboxes.forEach((cb) => {
      cb.disabled = false;
    });

    // Serialize saves to prevent out-of-order responses from corrupting state
    let saveQueue = Promise.resolve();

    // Attach click handler to each checkbox
    checkboxes.forEach((cb) => {
      cb.addEventListener('change', () => {
        const index = parseInt(cb.getAttribute('data-checkbox-index'), 10);
        const previousText = textarea.value;
        const newText = toggleCheckboxInMarkdown(previousText, index);
        textarea.value = newText;

        // POST the update
        const formData = new FormData();
        formData.append('action', 'update_text');
        formData.append('text', newText);
        formData.append('csrfmiddlewaretoken', getCsrfToken());

        document.dispatchEvent(new CustomEvent('save:start'));

        saveQueue = saveQueue.then(async () => {
          try {
            const response = await fetch(window.location.href, {
              method: 'POST',
              body: formData,
            });
            if (!response.ok) {
              console.error(
                `[checkbox_toggle] Save failed: ${response.status} ${response.statusText}`
              );
              // Revert only if no newer edits have been applied
              if (textarea.value === newText) {
                cb.checked = !cb.checked;
                textarea.value = previousText;
              }
              document.dispatchEvent(new CustomEvent('save:end', { detail: { ok: false } }));
            } else {
              document.dispatchEvent(new CustomEvent('save:end', { detail: { ok: true } }));
            }
          } catch (err) {
            console.error('[checkbox_toggle] Save error:', err);
            // Revert only if no newer edits have been applied
            if (textarea.value === newText) {
              cb.checked = !cb.checked;
              textarea.value = previousText;
            }
            document.dispatchEvent(new CustomEvent('save:end', { detail: { ok: false } }));
          }
        });
      });
    });
  }

  function init() {
    document.querySelectorAll('[data-text-card]').forEach(initTextCard);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
