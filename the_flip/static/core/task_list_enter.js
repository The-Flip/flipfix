/**
 * Task List Enter Module
 *
 * Auto-continues task list items when pressing Enter in textareas.
 * Works on any textarea with [data-task-list-enter].
 *
 * Behavior:
 * - Creates new unchecked item with same indentation
 * - Splits text if cursor is mid-line
 * - Removes prefix if line is empty
 * - Preserves blockquote prefixes ("> ")
 * - Supports unordered (-, *, +) and ordered (1., 2.) list markers
 */
(function () {
  'use strict';

  /**
   * Handle Enter key in textarea to auto-continue task lists.
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

  function init() {
    document.querySelectorAll('[data-task-list-enter]').forEach(initTaskListEnter);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
