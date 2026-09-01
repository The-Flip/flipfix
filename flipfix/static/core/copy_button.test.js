// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';

const { initCopyButtons } = require('./copy_button.js');

/** Build the markup invite_detail.html renders around the sign-up link. */
function buildMarkup(value = 'https://flipfix.example/register/abc/') {
  document.body.innerHTML = `
    <input id="invite-link" value="${value}">
    <button data-copy-target="#invite-link"><span data-copy-label>Copy</span></button>
    <p data-copy-status role="status" aria-live="polite"></p>
  `;
  return {
    button: document.querySelector('[data-copy-target]'),
    label: document.querySelector('[data-copy-label]'),
    status: document.querySelector('[data-copy-status]'),
  };
}

/** Install a clipboard stub; jsdom does not provide one. */
function stubClipboard(writeText) {
  Object.defineProperty(window.navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
    writable: true,
  });
}

describe('copy_button', () => {
  beforeEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
    delete window.navigator.clipboard;
    delete document.execCommand;
  });

  describe('clipboard API path', () => {
    it('copies the target input value', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      stubClipboard(writeText);
      const { button } = buildMarkup('https://flipfix.example/register/abc/');

      initCopyButtons(document);
      button.click();
      await vi.waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));

      expect(writeText).toHaveBeenCalledWith('https://flipfix.example/register/abc/');
    });

    it('announces success and flips the label', async () => {
      stubClipboard(vi.fn().mockResolvedValue(undefined));
      const { button, label, status } = buildMarkup();

      initCopyButtons(document);
      button.click();

      await vi.waitFor(() => expect(label.textContent).toBe('Copied'));
      expect(status.textContent).toBe('Link copied to the clipboard.');
    });
  });

  describe('insecure-context fallback', () => {
    it('falls back to execCommand when the clipboard API rejects', async () => {
      stubClipboard(vi.fn().mockRejectedValue(new Error('not allowed')));
      const execCommand = vi.fn().mockReturnValue(true);
      document.execCommand = execCommand;
      const { button, label } = buildMarkup();

      initCopyButtons(document);
      button.click();

      await vi.waitFor(() => expect(label.textContent).toBe('Copied'));
      expect(execCommand).toHaveBeenCalledWith('copy');
    });

    it('tells the user to press Ctrl+C when every path fails', async () => {
      const { button, label, status } = buildMarkup();

      initCopyButtons(document);
      button.click();

      await vi.waitFor(() => expect(label.textContent).toBe('Press Ctrl+C'));
      expect(status.textContent).toContain('press Ctrl+C');
    });
  });

  describe('wiring', () => {
    it('ignores a button whose target does not exist', () => {
      document.body.innerHTML = '<button data-copy-target="#missing">Copy</button>';
      expect(() => initCopyButtons(document)).not.toThrow();
    });

    it('keeps two copy buttons announcing into their own status regions', async () => {
      stubClipboard(vi.fn().mockResolvedValue(undefined));
      document.body.innerHTML = `
        <input id="first" value="one">
        <button data-copy-target="#first" data-copy-status="#first-status">
          <span data-copy-label>Copy</span>
        </button>
        <p id="first-status" data-copy-status></p>
        <input id="second" value="two">
        <button data-copy-target="#second" data-copy-status="#second-status">
          <span data-copy-label>Copy</span>
        </button>
        <p id="second-status" data-copy-status></p>
      `;
      initCopyButtons(document);

      document.querySelector('[data-copy-target="#second"]').click();

      await vi.waitFor(() =>
        expect(document.querySelector('#second-status').textContent).toBe(
          'Link copied to the clipboard.'
        )
      );
      expect(document.querySelector('#first-status').textContent).toBe('');
    });
  });
});
