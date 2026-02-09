/**
 * Markdown Shortcuts Module
 *
 * Enhances textareas with markdown editing shortcuts.
 * Auto-initializes on elements with [data-markdown-shortcuts].
 *
 * Features:
 * - Smart character wrapping: select text and type `, *, _
 *   to wrap instead of replace. Selection is preserved for stacking.
 * - Keyboard shortcuts: Cmd/Ctrl+B (bold), Cmd/Ctrl+I (italic),
 *   Cmd/Ctrl+K (insert link). Bold/italic toggle if already wrapped.
 * - Paste URL on selection: paste a URL with text selected to create
 *   a markdown link [selection](url).
 * - Tab indentation: Tab inserts 2 spaces, Shift+Tab removes up to 2
 *   leading spaces. Both work on multi-line selections.
 * - List Enter continuation: auto-continues list items on Enter key.
 *   Task lists get a new unchecked item; plain lists get a new item.
 *   Absorbed from task_list_enter.js.
 *
 * Dispatches 'input' event after changes for consistency with other modules.
 */
(function (exports) {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────

  const WRAP_PAIRS = {
    '`': ['`', '`'],
    '*': ['*', '*'],
    _: ['_', '_'],
  };

  const INDENT = '  ';

  // ── Pure Functions ─────────────────────────────────────────────
  //
  // Each function returns a replacement descriptor:
  //   { replaceStart, replaceEnd, replacement, selectionStart, selectionEnd }
  //
  // replaceStart..replaceEnd is the range in the original text to replace,
  // and replacement is the new text for that range. This enables
  // applyResult() to use execCommand('insertText') for surgical,
  // undo-safe editing rather than replacing the entire textarea value.

  /**
   * Wrap selected text with open/close characters.
   * Returns null if no selection (start === end).
   *
   * @param {string} value - textarea content
   * @param {number} start - selection start
   * @param {number} end - selection end
   * @param {string} open - opening character(s)
   * @param {string} close - closing character(s)
   * @returns {{ replaceStart: number, replaceEnd: number, replacement: string, selectionStart: number, selectionEnd: number } | null}
   */
  function wrapSelection(value, start, end, open, close) {
    if (start === end) return null;

    const selected = value.substring(start, end);

    return {
      replaceStart: start,
      replaceEnd: end,
      replacement: `${open}${selected}${close}`,
      selectionStart: start + open.length,
      selectionEnd: end + open.length,
    };
  }

  /**
   * Toggle a marker (bold/italic) around the selection.
   * If already wrapped, unwraps. If not, wraps.
   * With no selection, inserts empty markers with cursor between.
   *
   * @param {string} value - textarea content
   * @param {number} start - selection start
   * @param {number} end - selection end
   * @param {string} marker - e.g. '**' for bold, '*' for italic
   * @returns {{ replaceStart: number, replaceEnd: number, replacement: string, selectionStart: number, selectionEnd: number }}
   */
  function toggleMarker(value, start, end, marker) {
    const len = marker.length;

    if (start !== end) {
      const before = value.substring(start - len, start);
      const after = value.substring(end, end + len);

      if (before === marker && after === marker) {
        // Already wrapped: unwrap
        return {
          replaceStart: start - len,
          replaceEnd: end + len,
          replacement: value.substring(start, end),
          selectionStart: start - len,
          selectionEnd: end - len,
        };
      }

      // Not wrapped: wrap
      const selected = value.substring(start, end);
      return {
        replaceStart: start,
        replaceEnd: end,
        replacement: `${marker}${selected}${marker}`,
        selectionStart: start + len,
        selectionEnd: end + len,
      };
    }

    // No selection: insert empty markers, cursor between
    return {
      replaceStart: start,
      replaceEnd: end,
      replacement: `${marker}${marker}`,
      selectionStart: start + len,
      selectionEnd: start + len,
    };
  }

  /**
   * Insert a markdown link at the cursor/selection.
   * With selection: [selection](url) with "url" selected.
   * Without: [](url) with "url" selected.
   *
   * @param {string} value - textarea content
   * @param {number} start - selection start
   * @param {number} end - selection end
   * @returns {{ replaceStart: number, replaceEnd: number, replacement: string, selectionStart: number, selectionEnd: number }}
   */
  function insertLink(value, start, end) {
    if (start !== end) {
      const selected = value.substring(start, end);
      const linkText = `[${selected}](url)`;
      const urlStart = start + selected.length + 3;
      return {
        replaceStart: start,
        replaceEnd: end,
        replacement: linkText,
        selectionStart: urlStart,
        selectionEnd: urlStart + 3,
      };
    }

    const uStart = start + 3;
    return {
      replaceStart: start,
      replaceEnd: end,
      replacement: '[](url)',
      selectionStart: uStart,
      selectionEnd: uStart + 3,
    };
  }

  /**
   * Wrap selected text as a markdown link when pasting a URL.
   * Returns null if no selection, or if pasted text is not a URL.
   *
   * @param {string} value - textarea content
   * @param {number} start - selection start
   * @param {number} end - selection end
   * @param {string} pastedText - text from clipboard
   * @returns {{ replaceStart: number, replaceEnd: number, replacement: string, selectionStart: number, selectionEnd: number } | null}
   */
  function pasteLink(value, start, end, pastedText) {
    if (start === end) return null;
    if (!pastedText || !/^https?:\/\//.test(pastedText)) return null;

    const selected = value.substring(start, end);
    const link = `[${selected}](${pastedText})`;

    return {
      replaceStart: start,
      replaceEnd: end,
      replacement: link,
      selectionStart: start,
      selectionEnd: start + link.length,
    };
  }

  /**
   * Indent or dedent lines covered by the selection.
   * With no selection: indents the current line by 2 spaces.
   *
   * @param {string} value - textarea content
   * @param {number} start - selection start
   * @param {number} end - selection end
   * @param {boolean} dedent - true to remove indentation
   * @returns {{ replaceStart: number, replaceEnd: number, replacement: string, selectionStart: number, selectionEnd: number }}
   */
  function indentLines(value, start, end, dedent) {
    // Find the full lines encompassing the selection
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    let lineEnd = value.indexOf('\n', end);
    if (lineEnd === -1) lineEnd = value.length;

    const selectedLines = value.substring(lineStart, lineEnd);
    const lines = selectedLines.split('\n');

    let selectionDelta = 0;
    let totalDelta = 0;

    let newLines;
    if (dedent) {
      newLines = lines.map((line, i) => {
        let spacesToRemove = 0;
        if (line.startsWith('  ')) spacesToRemove = 2;
        else if (line.startsWith(' ')) spacesToRemove = 1;

        if (i === 0) selectionDelta = -spacesToRemove;
        totalDelta -= spacesToRemove;
        return line.substring(spacesToRemove);
      });
    } else {
      newLines = lines.map((line, i) => {
        if (i === 0) selectionDelta = INDENT.length;
        totalDelta += INDENT.length;
        return INDENT + line;
      });
    }

    const newText = newLines.join('\n');
    const newStart = Math.max(lineStart, start + selectionDelta);
    const newEnd = Math.max(newStart, end + totalDelta);

    return {
      replaceStart: lineStart,
      replaceEnd: lineEnd,
      replacement: newText,
      selectionStart: newStart,
      selectionEnd: newEnd,
    };
  }

  /**
   * Handle Enter key on a list line (task lists and plain lists).
   * Returns null if the current line is not a list item,
   * or if there is a selection (start !== end).
   *
   * @param {string} value - textarea content
   * @param {number} start - cursor position (selectionStart)
   * @param {number} end - cursor position (selectionEnd)
   * @returns {{ replaceStart: number, replaceEnd: number, replacement: string, selectionStart: number, selectionEnd: number } | null}
   */
  function listEnter(value, start, end) {
    // Don't interfere if there's a selection
    if (start !== end) return null;

    // Find the current line boundaries
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    let lineEnd = value.indexOf('\n', start);
    if (lineEnd === -1) lineEnd = value.length;

    // Get text before and after cursor on this line
    const beforeCursor = value.substring(lineStart, start);
    const afterCursor = value.substring(start, lineEnd);

    // Try task list first: optional blockquote, optional indent, list marker, checkbox
    const match = beforeCursor.match(/^((?:>\s*)*\s*)([-*+]|\d+\.) \[(?: *|[xX])\] ?(.*)$/);
    if (match) {
      const [, prefix, marker, contentBeforeCursor] = match;

      // Empty checkbox line: remove prefix
      if (contentBeforeCursor.trim() === '' && afterCursor.trim() === '') {
        return {
          replaceStart: lineStart,
          replaceEnd: lineEnd,
          replacement: prefix,
          selectionStart: lineStart + prefix.length,
          selectionEnd: lineStart + prefix.length,
        };
      }

      let newMarker = marker;
      if (/^\d+\.$/.test(marker)) {
        newMarker = `${parseInt(marker) + 1}.`;
      }

      const newLine = `\n${prefix}${newMarker} [ ] ${afterCursor}`;
      const cursorPos = start + `\n${prefix}${newMarker} [ ] `.length;

      return {
        replaceStart: start,
        replaceEnd: lineEnd,
        replacement: newLine,
        selectionStart: cursorPos,
        selectionEnd: cursorPos,
      };
    }

    // Plain list: optional blockquote, optional indent, list marker, content
    const listMatch = beforeCursor.match(/^((?:>\s*)*\s*)([-*+]|\d+\.) (.*)$/);
    if (!listMatch) return null;

    const [, listPrefix, listMarker, listContent] = listMatch;

    // Empty list line: remove prefix
    if (listContent.trim() === '' && afterCursor.trim() === '') {
      return {
        replaceStart: lineStart,
        replaceEnd: lineEnd,
        replacement: listPrefix,
        selectionStart: lineStart + listPrefix.length,
        selectionEnd: lineStart + listPrefix.length,
      };
    }

    let newListMarker = listMarker;
    if (/^\d+\.$/.test(listMarker)) {
      newListMarker = `${parseInt(listMarker) + 1}.`;
    }

    const listNewLine = `\n${listPrefix}${newListMarker} ${afterCursor}`;
    const listCursorPos = start + `\n${listPrefix}${newListMarker} `.length;

    return {
      replaceStart: start,
      replaceEnd: lineEnd,
      replacement: listNewLine,
      selectionStart: listCursorPos,
      selectionEnd: listCursorPos,
    };
  }

  // ── DOM Wiring (browser only) ─────────────────────────────────

  if (typeof document !== 'undefined') {
    /**
     * Apply a pure function result to a textarea, preserving undo.
     *
     * Uses execCommand('insertText') to keep the browser's undo stack
     * intact (Cmd/Ctrl+Z). Despite being "deprecated", it remains the
     * only way to programmatically edit a textarea with undo support.
     * Falls back to direct .value assignment in environments that don't
     * support it (e.g. jsdom in tests).
     */
    function applyResult(textarea, result) {
      if (!result) return false;

      textarea.selectionStart = result.replaceStart;
      textarea.selectionEnd = result.replaceEnd;
      if (!document.execCommand('insertText', false, result.replacement)) {
        const before = textarea.value.substring(0, result.replaceStart);
        const after = textarea.value.substring(result.replaceEnd);
        textarea.value = `${before}${result.replacement}${after}`;
      }

      textarea.selectionStart = result.selectionStart;
      textarea.selectionEnd = result.selectionEnd;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    }

    function initMarkdownShortcuts(textarea) {
      textarea.addEventListener('paste', (e) => {
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        if (start === end) return;

        if (!e.clipboardData) return;
        const pastedText = e.clipboardData.getData('text');
        const result = pasteLink(textarea.value, start, end, pastedText);
        if (result) {
          e.preventDefault();
          applyResult(textarea, result);
        }
      });

      textarea.addEventListener('keydown', (e) => {
        if (e.isComposing) return;
        if (e.defaultPrevented) return;

        const value = textarea.value;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const isMod = e.metaKey || e.ctrlKey;

        // 1. Keyboard shortcuts (Cmd/Ctrl + B, I, K)
        if (isMod) {
          if (e.key === 'b' || e.key === 'B') {
            e.preventDefault();
            applyResult(textarea, toggleMarker(value, start, end, '**'));
            return;
          }
          if (e.key === 'i' || e.key === 'I') {
            e.preventDefault();
            applyResult(textarea, toggleMarker(value, start, end, '*'));
            return;
          }
          if (e.key === 'k' || e.key === 'K') {
            e.preventDefault();
            applyResult(textarea, insertLink(value, start, end));
            return;
          }
        }

        // 2. Tab / Shift+Tab indentation
        if (e.key === 'Tab') {
          e.preventDefault();
          applyResult(textarea, indentLines(value, start, end, e.shiftKey));
          return;
        }

        // 3. List Enter continuation
        if (e.key === 'Enter') {
          const result = listEnter(value, start, end);
          if (result) {
            e.preventDefault();
            applyResult(textarea, result);
          }
          return;
        }

        // 4. Smart character wrapping (only when there's a selection)
        const pair = WRAP_PAIRS[e.key];
        if (pair && start !== end) {
          e.preventDefault();
          applyResult(textarea, wrapSelection(value, start, end, pair[0], pair[1]));
        }
      });
    }

    function init() {
      document.querySelectorAll('[data-markdown-shortcuts]').forEach(initMarkdownShortcuts);
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  // ── Test Exports (Node only) ──────────────────────────────────

  if (exports) {
    exports.wrapSelection = wrapSelection;
    exports.toggleMarker = toggleMarker;
    exports.insertLink = insertLink;
    exports.pasteLink = pasteLink;
    exports.indentLines = indentLines;
    exports.listEnter = listEnter;
  }
})(typeof module !== 'undefined' ? module.exports : null);
