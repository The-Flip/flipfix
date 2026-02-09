import { describe, it, expect } from 'vitest';

const { toggleCheckboxInMarkdown } = require('./checkbox_toggle.js');

// ── Basic Toggle ────────────────────────────────────────────────

describe('toggleCheckboxInMarkdown', () => {
  describe('basic toggle', () => {
    it('checks an unchecked checkbox', () => {
      expect(toggleCheckboxInMarkdown('- [ ] Buy milk', 0)).toBe('- [x] Buy milk');
    });

    it('unchecks a checked checkbox', () => {
      expect(toggleCheckboxInMarkdown('- [x] Buy milk', 0)).toBe('- [ ] Buy milk');
    });

    it('unchecks an uppercase X checkbox', () => {
      expect(toggleCheckboxInMarkdown('- [X] Buy milk', 0)).toBe('- [ ] Buy milk');
    });

    it('returns text unchanged when index is out of range', () => {
      const text = '- [ ] Only one item';
      expect(toggleCheckboxInMarkdown(text, 5)).toBe(text);
    });
  });

  // ── Index Targeting ─────────────────────────────────────────

  describe('index targeting', () => {
    const list = '- [ ] First\n- [x] Second\n- [ ] Third';

    it('toggles only the first checkbox when index is 0', () => {
      expect(toggleCheckboxInMarkdown(list, 0)).toBe('- [x] First\n- [x] Second\n- [ ] Third');
    });

    it('toggles only the second checkbox when index is 1', () => {
      expect(toggleCheckboxInMarkdown(list, 1)).toBe('- [ ] First\n- [ ] Second\n- [ ] Third');
    });

    it('toggles the last checkbox in a multi-item list', () => {
      expect(toggleCheckboxInMarkdown(list, 2)).toBe('- [ ] First\n- [x] Second\n- [x] Third');
    });
  });

  // ── List Marker Variants ────────────────────────────────────

  describe('list marker variants', () => {
    it('works with dash marker (-)', () => {
      expect(toggleCheckboxInMarkdown('- [ ] task', 0)).toBe('- [x] task');
    });

    it('works with asterisk marker (*)', () => {
      expect(toggleCheckboxInMarkdown('* [ ] task', 0)).toBe('* [x] task');
    });

    it('works with plus marker (+)', () => {
      expect(toggleCheckboxInMarkdown('+ [ ] task', 0)).toBe('+ [x] task');
    });

    it('works with numbered marker (1.)', () => {
      expect(toggleCheckboxInMarkdown('1. [ ] task', 0)).toBe('1. [x] task');
    });

    it('works with multi-digit numbered marker (12.)', () => {
      expect(toggleCheckboxInMarkdown('12. [ ] task', 0)).toBe('12. [x] task');
    });
  });

  // ── Blockquote Prefix ──────────────────────────────────────

  describe('blockquote prefix', () => {
    it('toggles checkbox inside a blockquote', () => {
      expect(toggleCheckboxInMarkdown('> - [ ] quoted task', 0)).toBe('> - [x] quoted task');
    });

    it('toggles checkbox inside a nested blockquote', () => {
      expect(toggleCheckboxInMarkdown('> > - [ ] nested', 0)).toBe('> > - [x] nested');
    });
  });

  // ── Code Block Exclusion ───────────────────────────────────

  describe('code block exclusion', () => {
    it('skips markers inside backtick-fenced code blocks', () => {
      const text = '- [ ] real task\n```\n- [ ] in code\n```';
      expect(toggleCheckboxInMarkdown(text, 0)).toBe('- [x] real task\n```\n- [ ] in code\n```');
    });

    it('skips markers inside tilde-fenced code blocks', () => {
      const text = '- [ ] real task\n~~~\n- [ ] in code\n~~~';
      expect(toggleCheckboxInMarkdown(text, 0)).toBe('- [x] real task\n~~~\n- [ ] in code\n~~~');
    });

    it('skips markers inside fenced code blocks with language specifier', () => {
      const text = '- [ ] real task\n```js\n- [ ] in code\n```';
      expect(toggleCheckboxInMarkdown(text, 0)).toBe('- [x] real task\n```js\n- [ ] in code\n```');
    });

    it('counts correctly when checkbox appears after a code block', () => {
      const text = '- [ ] before\n```\n- [ ] in code\n```\n- [ ] after';
      // Index 1 should target "after" (skipping the code block marker)
      expect(toggleCheckboxInMarkdown(text, 1)).toBe(
        '- [ ] before\n```\n- [ ] in code\n```\n- [x] after'
      );
    });

    it('handles code block between real checkboxes', () => {
      const text = '- [ ] first\n```\n- [ ] fake\n- [ ] also fake\n```\n- [ ] second';
      // Index 0 = "first", index 1 = "second" (code block items skipped)
      expect(toggleCheckboxInMarkdown(text, 0)).toBe(
        '- [x] first\n```\n- [ ] fake\n- [ ] also fake\n```\n- [ ] second'
      );
      expect(toggleCheckboxInMarkdown(text, 1)).toBe(
        '- [ ] first\n```\n- [ ] fake\n- [ ] also fake\n```\n- [x] second'
      );
    });
  });

  // ── Edge Cases ─────────────────────────────────────────────

  describe('edge cases', () => {
    it('returns text unchanged when there are no checkboxes', () => {
      const text = 'Just some regular text\nwith multiple lines';
      expect(toggleCheckboxInMarkdown(text, 0)).toBe(text);
    });

    it('returns empty string unchanged', () => {
      expect(toggleCheckboxInMarkdown('', 0)).toBe('');
    });

    it('toggles checkbox with multiple spaces', () => {
      expect(toggleCheckboxInMarkdown('- [  ] task', 0)).toBe('- [x] task');
    });

    it('preserves all surrounding text', () => {
      const text = 'Intro paragraph\n\n- [ ] the task\n\nOutro paragraph';
      expect(toggleCheckboxInMarkdown(text, 0)).toBe(
        'Intro paragraph\n\n- [x] the task\n\nOutro paragraph'
      );
    });

    it('handles checkbox on the first line', () => {
      expect(toggleCheckboxInMarkdown('- [ ] first line task', 0)).toBe('- [x] first line task');
    });

    it('handles checkbox on the last line without trailing newline', () => {
      const text = 'Some text\n- [ ] last';
      expect(toggleCheckboxInMarkdown(text, 0)).toBe('Some text\n- [x] last');
    });
  });
});
