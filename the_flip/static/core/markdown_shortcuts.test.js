import { describe, it, expect } from 'vitest';

const {
  wrapSelection,
  toggleMarker,
  insertLink,
  pasteLink,
  indentLines,
  listEnter,
} = require('./markdown_shortcuts.js');

// Helper: reconstruct full text from original + replacement result
function apply(original, result) {
  return `${original.substring(0, result.replaceStart)}${result.replacement}${original.substring(result.replaceEnd)}`;
}

// ── Smart Wrapping ──────────────────────────────────────────────

describe('wrapSelection', () => {
  it('wraps selected text with backticks', () => {
    const result = wrapSelection('hello world', 0, 5, '`', '`');
    expect(apply('hello world', result)).toBe('`hello` world');
    expect(result.selectionStart).toBe(1);
    expect(result.selectionEnd).toBe(6);
  });

  it('wraps selected text with asterisks', () => {
    const result = wrapSelection('hello world', 0, 5, '*', '*');
    expect(apply('hello world', result)).toBe('*hello* world');
    expect(result.selectionStart).toBe(1);
    expect(result.selectionEnd).toBe(6);
  });

  it('wraps selected text with underscores', () => {
    const result = wrapSelection('hello world', 0, 5, '_', '_');
    expect(apply('hello world', result)).toBe('_hello_ world');
    expect(result.selectionStart).toBe(1);
    expect(result.selectionEnd).toBe(6);
  });

  it('returns null when no selection', () => {
    const result = wrapSelection('hello world', 3, 3, '`', '`');
    expect(result).toBeNull();
  });

  it('wraps mid-text selection', () => {
    const result = wrapSelection('hello world', 6, 11, '*', '*');
    expect(apply('hello world', result)).toBe('hello *world*');
    expect(result.selectionStart).toBe(7);
    expect(result.selectionEnd).toBe(12);
  });

  it('enables stacking: wrap with * then * again produces **text**', () => {
    // First wrap
    const first = wrapSelection('hello', 0, 5, '*', '*');
    const v1 = apply('hello', first);
    expect(v1).toBe('*hello*');
    expect(first.selectionStart).toBe(1);
    expect(first.selectionEnd).toBe(6);

    // Second wrap on the same inner selection
    const second = wrapSelection(v1, first.selectionStart, first.selectionEnd, '*', '*');
    expect(apply(v1, second)).toBe('**hello**');
    expect(second.selectionStart).toBe(2);
    expect(second.selectionEnd).toBe(7);
  });
});

// ── Bold / Italic Toggle ────────────────────────────────────────

describe('toggleMarker', () => {
  describe('bold (**)', () => {
    it('wraps selected text with **', () => {
      const result = toggleMarker('hello world', 0, 5, '**');
      expect(apply('hello world', result)).toBe('**hello** world');
      expect(result.selectionStart).toBe(2);
      expect(result.selectionEnd).toBe(7);
    });

    it('unwraps if already bolded', () => {
      const result = toggleMarker('**hello** world', 2, 7, '**');
      expect(apply('**hello** world', result)).toBe('hello world');
      expect(result.selectionStart).toBe(0);
      expect(result.selectionEnd).toBe(5);
    });

    it('inserts empty markers with cursor between when no selection', () => {
      const result = toggleMarker('hello world', 5, 5, '**');
      expect(apply('hello world', result)).toBe('hello**** world');
      expect(result.selectionStart).toBe(7);
      expect(result.selectionEnd).toBe(7);
    });

    it('wraps when selection is at start of text', () => {
      const result = toggleMarker('hello', 0, 5, '**');
      expect(apply('hello', result)).toBe('**hello**');
      expect(result.selectionStart).toBe(2);
      expect(result.selectionEnd).toBe(7);
    });

    it('does not unwrap when only one side matches', () => {
      // **hello without closing **
      const result = toggleMarker('**hello world', 2, 7, '**');
      expect(apply('**hello world', result)).toBe('****hello** world');
      expect(result.selectionStart).toBe(4);
      expect(result.selectionEnd).toBe(9);
    });
  });

  describe('italic (*)', () => {
    it('wraps selected text with *', () => {
      const result = toggleMarker('hello world', 0, 5, '*');
      expect(apply('hello world', result)).toBe('*hello* world');
      expect(result.selectionStart).toBe(1);
      expect(result.selectionEnd).toBe(6);
    });

    it('unwraps if already italicized', () => {
      const result = toggleMarker('*hello* world', 1, 6, '*');
      expect(apply('*hello* world', result)).toBe('hello world');
      expect(result.selectionStart).toBe(0);
      expect(result.selectionEnd).toBe(5);
    });

    it('inserts empty markers with cursor between when no selection', () => {
      const result = toggleMarker('hello world', 5, 5, '*');
      expect(apply('hello world', result)).toBe('hello** world');
      expect(result.selectionStart).toBe(6);
      expect(result.selectionEnd).toBe(6);
    });
  });
});

// ── Insert Link ─────────────────────────────────────────────────

describe('insertLink', () => {
  it('wraps selected text as link with url placeholder selected', () => {
    const result = insertLink('hello world', 0, 5);
    expect(apply('hello world', result)).toBe('[hello](url) world');
    // "url" should be selected
    expect(result.selectionStart).toBe(8);
    expect(result.selectionEnd).toBe(11);
  });

  it('inserts empty link template when no selection', () => {
    const result = insertLink('hello world', 5, 5);
    expect(apply('hello world', result)).toBe('hello[](url) world');
    // "url" should be selected
    expect(result.selectionStart).toBe(8);
    expect(result.selectionEnd).toBe(11);
  });

  it('works at end of text', () => {
    const result = insertLink('hello', 5, 5);
    expect(apply('hello', result)).toBe('hello[](url)');
    expect(result.selectionStart).toBe(8);
    expect(result.selectionEnd).toBe(11);
  });
});

// ── Paste Link ──────────────────────────────────────────────────

describe('pasteLink', () => {
  it('wraps selected text as link when pasting a URL', () => {
    const result = pasteLink('hello world', 0, 5, 'https://example.com');
    expect(apply('hello world', result)).toBe('[hello](https://example.com) world');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(28);
  });

  it('works with http URLs', () => {
    const result = pasteLink('click here', 0, 5, 'http://example.com');
    expect(apply('click here', result)).toBe('[click](http://example.com) here');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(27);
  });

  it('returns null when no selection', () => {
    const result = pasteLink('hello', 3, 3, 'https://example.com');
    expect(result).toBeNull();
  });

  it('returns null when pasted text is not a URL', () => {
    const result = pasteLink('hello world', 0, 5, 'just some text');
    expect(result).toBeNull();
  });

  it('returns null when pasted text is empty', () => {
    const result = pasteLink('hello world', 0, 5, '');
    expect(result).toBeNull();
  });

  it('wraps mid-text selection', () => {
    const result = pasteLink('see the docs for info', 8, 12, 'https://docs.example.com');
    expect(apply('see the docs for info', result)).toBe(
      'see the [docs](https://docs.example.com) for info'
    );
    expect(result.selectionStart).toBe(8);
    expect(result.selectionEnd).toBe(40);
  });

  it('handles URL with path and query', () => {
    const result = pasteLink('link', 0, 4, 'https://example.com/path?q=1&b=2');
    expect(apply('link', result)).toBe('[link](https://example.com/path?q=1&b=2)');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(40);
  });
});

// ── Tab Indentation ─────────────────────────────────────────────

describe('indentLines', () => {
  it('inserts 2 spaces at cursor when no selection', () => {
    const text = 'hello';
    const result = indentLines(text, 0, 0, false);
    expect(apply(text, result)).toBe('  hello');
    expect(result.selectionStart).toBe(2);
    expect(result.selectionEnd).toBe(2);
  });

  it('indents single line when selection is within it', () => {
    const text = 'hello world';
    const result = indentLines(text, 0, 5, false);
    expect(apply(text, result)).toBe('  hello world');
    expect(result.selectionStart).toBe(2);
    expect(result.selectionEnd).toBe(7);
  });

  it('indents multiple selected lines', () => {
    const text = 'line1\nline2\nline3';
    const result = indentLines(text, 0, 17, false);
    expect(apply(text, result)).toBe('  line1\n  line2\n  line3');
    expect(result.selectionStart).toBe(2);
    expect(result.selectionEnd).toBe(23);
  });

  it('indents only the lines covered by the selection', () => {
    // Select from middle of line1 to middle of line2
    const text = 'line1\nline2\nline3';
    const result = indentLines(text, 3, 9, false);
    expect(apply(text, result)).toBe('  line1\n  line2\nline3');
    expect(result.selectionStart).toBe(5);
    expect(result.selectionEnd).toBe(13);
  });

  it('dedents by removing up to 2 leading spaces', () => {
    const text = '  hello';
    const result = indentLines(text, 0, 7, true);
    expect(apply(text, result)).toBe('hello');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(5);
  });

  it('dedents removes only 1 space if only 1 present', () => {
    const text = ' hello';
    const result = indentLines(text, 0, 6, true);
    expect(apply(text, result)).toBe('hello');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(5);
  });

  it('dedents does nothing on unindented line', () => {
    const text = 'hello';
    const result = indentLines(text, 0, 5, true);
    expect(apply(text, result)).toBe('hello');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(5);
  });

  it('dedents multiple lines', () => {
    const text = '  line1\n  line2\n  line3';
    const result = indentLines(text, 0, 23, true);
    expect(apply(text, result)).toBe('line1\nline2\nline3');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(17);
  });

  it('handles cursor-only dedent on indented line', () => {
    const text = '  hello';
    const result = indentLines(text, 2, 2, true);
    expect(apply(text, result)).toBe('hello');
    expect(result.selectionStart).toBe(0);
  });
});

// ── Task List Enter ─────────────────────────────────────────────

describe('listEnter', () => {
  it('creates new unchecked item after - [ ] line', () => {
    const text = '- [ ] hello';
    const result = listEnter(text, 11, 11);
    expect(apply(text, result)).toBe('- [ ] hello\n- [ ] ');
    expect(result.selectionStart).toBe(18);
    expect(result.selectionEnd).toBe(18);
  });

  it('creates new item with * marker', () => {
    const text = '* [ ] hello';
    const result = listEnter(text, 11, 11);
    expect(apply(text, result)).toBe('* [ ] hello\n* [ ] ');
    expect(result.selectionStart).toBe(18);
    expect(result.selectionEnd).toBe(18);
  });

  it('creates new item with + marker', () => {
    const text = '+ [ ] hello';
    const result = listEnter(text, 11, 11);
    expect(apply(text, result)).toBe('+ [ ] hello\n+ [ ] ');
    expect(result.selectionStart).toBe(18);
    expect(result.selectionEnd).toBe(18);
  });

  it('creates unchecked item from checked [x] line', () => {
    const text = '- [x] hello';
    const result = listEnter(text, 11, 11);
    expect(apply(text, result)).toBe('- [x] hello\n- [ ] ');
    expect(result.selectionStart).toBe(18);
    expect(result.selectionEnd).toBe(18);
  });

  it('creates unchecked item from checked [X] line', () => {
    const text = '- [X] hello';
    const result = listEnter(text, 11, 11);
    expect(apply(text, result)).toBe('- [X] hello\n- [ ] ');
    expect(result.selectionStart).toBe(18);
    expect(result.selectionEnd).toBe(18);
  });

  it('creates item from no-space checkbox []', () => {
    const text = '- [] hello';
    const result = listEnter(text, 10, 10);
    expect(apply(text, result)).toBe('- [] hello\n- [ ] ');
    expect(result.selectionStart).toBe(17);
    expect(result.selectionEnd).toBe(17);
  });

  it('removes prefix on empty task list line', () => {
    const text = '- [ ] ';
    const result = listEnter(text, 6, 6);
    expect(apply(text, result)).toBe('');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(0);
  });

  it('removes prefix on empty checkbox-only line', () => {
    const text = 'first line\n- [ ] ';
    const result = listEnter(text, 17, 17);
    expect(apply(text, result)).toBe('first line\n');
    expect(result.selectionStart).toBe(11);
    expect(result.selectionEnd).toBe(11);
  });

  it('increments numbered list marker', () => {
    const text = '1. [ ] hello';
    const result = listEnter(text, 12, 12);
    expect(apply(text, result)).toBe('1. [ ] hello\n2. [ ] ');
    expect(result.selectionStart).toBe(20);
    expect(result.selectionEnd).toBe(20);
  });

  it('preserves blockquote prefix', () => {
    const text = '> - [ ] hello';
    const result = listEnter(text, 13, 13);
    expect(apply(text, result)).toBe('> - [ ] hello\n> - [ ] ');
    expect(result.selectionStart).toBe(22);
    expect(result.selectionEnd).toBe(22);
  });

  it('preserves nested blockquote prefix', () => {
    const text = '> > - [ ] hello';
    const result = listEnter(text, 15, 15);
    expect(apply(text, result)).toBe('> > - [ ] hello\n> > - [ ] ');
    expect(result.selectionStart).toBe(26);
    expect(result.selectionEnd).toBe(26);
  });

  it('splits text when cursor is mid-line', () => {
    const text = '- [ ] hello world';
    const result = listEnter(text, 11, 11);
    expect(apply(text, result)).toBe('- [ ] hello\n- [ ]  world');
    expect(result.selectionStart).toBe(18);
    expect(result.selectionEnd).toBe(18);
  });

  it('returns null for non-task-list line', () => {
    const result = listEnter('just a normal line', 18, 18);
    expect(result).toBeNull();
  });

  it('continues unordered list with - marker', () => {
    const text = '- plain list item';
    const result = listEnter(text, 17, 17);
    expect(apply(text, result)).toBe('- plain list item\n- ');
    expect(result.selectionStart).toBe(20);
    expect(result.selectionEnd).toBe(20);
  });

  it('continues unordered list with * marker', () => {
    const text = '* item one';
    const result = listEnter(text, 10, 10);
    expect(apply(text, result)).toBe('* item one\n* ');
    expect(result.selectionStart).toBe(13);
    expect(result.selectionEnd).toBe(13);
  });

  it('continues unordered list with + marker', () => {
    const text = '+ item one';
    const result = listEnter(text, 10, 10);
    expect(apply(text, result)).toBe('+ item one\n+ ');
    expect(result.selectionStart).toBe(13);
    expect(result.selectionEnd).toBe(13);
  });

  it('continues ordered list and increments number', () => {
    const text = '1. first item';
    const result = listEnter(text, 13, 13);
    expect(apply(text, result)).toBe('1. first item\n2. ');
    expect(result.selectionStart).toBe(17);
    expect(result.selectionEnd).toBe(17);
  });

  it('removes prefix on empty plain list line', () => {
    const text = '- ';
    const result = listEnter(text, 2, 2);
    expect(apply(text, result)).toBe('');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(0);
  });

  it('removes prefix on empty ordered list line', () => {
    const text = '1. ';
    const result = listEnter(text, 3, 3);
    expect(apply(text, result)).toBe('');
    expect(result.selectionStart).toBe(0);
    expect(result.selectionEnd).toBe(0);
  });

  it('continues indented plain list', () => {
    const text = '  - nested item';
    const result = listEnter(text, 15, 15);
    expect(apply(text, result)).toBe('  - nested item\n  - ');
    expect(result.selectionStart).toBe(20);
    expect(result.selectionEnd).toBe(20);
  });

  it('splits plain list text when cursor is mid-line', () => {
    const text = '- hello world';
    const result = listEnter(text, 7, 7);
    expect(apply(text, result)).toBe('- hello\n-  world');
    expect(result.selectionStart).toBe(10);
    expect(result.selectionEnd).toBe(10);
  });

  it('preserves blockquote prefix on plain list', () => {
    const text = '> - hello';
    const result = listEnter(text, 9, 9);
    expect(apply(text, result)).toBe('> - hello\n> - ');
    expect(result.selectionStart).toBe(14);
    expect(result.selectionEnd).toBe(14);
  });

  it('returns null for non-list line', () => {
    const result = listEnter('just a normal line', 18, 18);
    expect(result).toBeNull();
  });

  it('returns null when there is a selection', () => {
    const result = listEnter('- [ ] hello', 2, 8);
    expect(result).toBeNull();
  });

  it('handles task list on non-first line', () => {
    const text = 'some intro\n- [ ] task one';
    const cursor = text.length;
    const result = listEnter(text, cursor, cursor);
    expect(apply(text, result)).toBe('some intro\n- [ ] task one\n- [ ] ');
    expect(result.selectionStart).toBe(text.length + 7);
  });

  it('preserves indentation prefix', () => {
    const text = '  - [ ] indented';
    const result = listEnter(text, 16, 16);
    expect(apply(text, result)).toBe('  - [ ] indented\n  - [ ] ');
    expect(result.selectionStart).toBe(25);
    expect(result.selectionEnd).toBe(25);
  });

  it('handles two-space checkbox [  ]', () => {
    const text = '- [  ] hello';
    const result = listEnter(text, 12, 12);
    expect(apply(text, result)).toBe('- [  ] hello\n- [ ] ');
    expect(result.selectionStart).toBe(19);
    expect(result.selectionEnd).toBe(19);
  });

  it('handles three-space checkbox [   ]', () => {
    const text = '- [   ] hello';
    const result = listEnter(text, 13, 13);
    expect(apply(text, result)).toBe('- [   ] hello\n- [ ] ');
    expect(result.selectionStart).toBe(20);
    expect(result.selectionEnd).toBe(20);
  });

  it('continues nested list at 2-space indent level', () => {
    const text = '- [ ] parent\n  - [ ] child';
    const cursor = text.length;
    const result = listEnter(text, cursor, cursor);
    expect(apply(text, result)).toBe('- [ ] parent\n  - [ ] child\n  - [ ] ');
    expect(result.selectionStart).toBe(text.length + 9);
  });

  it('continues nested list at 4-space indent level', () => {
    const text = '- [ ] parent\n  - [ ] child\n    - [ ] grandchild';
    const cursor = text.length;
    const result = listEnter(text, cursor, cursor);
    expect(apply(text, result)).toBe(
      '- [ ] parent\n  - [ ] child\n    - [ ] grandchild\n    - [ ] '
    );
    expect(result.selectionStart).toBe(text.length + 11);
  });

  it('removes prefix on empty nested line', () => {
    const text = '- [ ] parent\n  - [ ] ';
    const cursor = text.length;
    const result = listEnter(text, cursor, cursor);
    // Empty nested item: strip marker, keep indent prefix
    expect(apply(text, result)).toBe('- [ ] parent\n  ');
    expect(result.selectionStart).toBe(15);
    expect(result.selectionEnd).toBe(15);
  });
});

// ── Integration Tests ────────────────────────────────────────────

// Shared helper: creates a jsdom instance with the module loaded
async function createDom(textareaContent) {
  const { JSDOM } = await import('jsdom');
  const fs = await import('fs');
  const { fileURLToPath } = await import('url');
  const path = await import('path');

  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const scriptContent = fs.readFileSync(path.join(__dirname, 'markdown_shortcuts.js'), 'utf8');

  const dom = new JSDOM(
    `<!DOCTYPE html><textarea data-markdown-shortcuts>${textareaContent}</textarea>`,
    { runScripts: 'dangerously' }
  );
  const doc = dom.window.document;
  const textarea = doc.querySelector('textarea');

  // Polyfill execCommand (jsdom doesn't implement it).
  // Return false so applyResult uses the .value fallback.
  const polyfill = doc.createElement('script');
  polyfill.textContent = 'document.execCommand = function() { return false; };';
  doc.head.appendChild(polyfill);

  const script = doc.createElement('script');
  script.textContent = scriptContent;
  doc.head.appendChild(script);

  return { dom, textarea };
}

describe('IME guard (integration)', () => {
  it('does not transform when isComposing is true', async () => {
    const { dom, textarea } = await createDom('hello');
    textarea.selectionStart = 0;
    textarea.selectionEnd = 5;

    const event = new dom.window.KeyboardEvent('keydown', {
      key: '`',
      bubbles: true,
      cancelable: true,
    });
    Object.defineProperty(event, 'isComposing', { value: true });
    textarea.dispatchEvent(event);

    expect(textarea.value).toBe('hello');
    expect(textarea.selectionStart).toBe(0);
    expect(textarea.selectionEnd).toBe(5);
  });
});

describe('defaultPrevented guard (integration)', () => {
  it('does not transform when another handler already prevented the event', async () => {
    const { dom, textarea } = await createDom('- hello');
    textarea.selectionStart = 7;
    textarea.selectionEnd = 7;

    // Simulate another handler (e.g. link_autocomplete) having called preventDefault()
    const event = new dom.window.KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    });
    event.preventDefault();
    textarea.dispatchEvent(event);

    // Should NOT insert a new list item
    expect(textarea.value).toBe('- hello');
  });
});

describe('paste clipboardData guard (integration)', () => {
  it('does not throw when clipboardData is unavailable', async () => {
    const { dom, textarea } = await createDom('hello');
    textarea.selectionStart = 0;
    textarea.selectionEnd = 5;

    // Dispatch a paste event without clipboardData
    const event = new dom.window.Event('paste', {
      bubbles: true,
      cancelable: true,
    });
    textarea.dispatchEvent(event);

    expect(textarea.value).toBe('hello');
  });
});
