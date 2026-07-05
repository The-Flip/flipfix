// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { initSubmitGuard } = require('./submit_guard.js');

function buildForm({ required = false } = {}) {
  const form = document.createElement('form');
  const input = document.createElement('input');
  input.name = 'text';
  if (required) {
    input.required = true;
  }
  const button = document.createElement('button');
  button.type = 'submit';
  button.textContent = 'Log It';
  form.append(input, button);
  document.body.appendChild(form);
  return { form, input, button };
}

function submit(form) {
  form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  vi.runAllTimers();
}

describe('initSubmitGuard', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('disables and relabels the submit button on a valid submit', () => {
    const { form, button } = buildForm();
    initSubmitGuard(form);

    submit(form);

    expect(button.disabled).toBe(true);
    expect(button.textContent).toBe('Logging…');
  });

  it('does not disable the button when HTML5 validation fails', () => {
    const { form, button } = buildForm({ required: true });
    initSubmitGuard(form);

    submit(form);

    expect(button.disabled).toBe(false);
    expect(button.textContent).toBe('Log It');
  });

  it('honors a per-button data-busy-label', () => {
    const { form, button } = buildForm();
    button.dataset.busyLabel = 'Saving…';
    initSubmitGuard(form);

    submit(form);

    expect(button.textContent).toBe('Saving…');
  });
});
