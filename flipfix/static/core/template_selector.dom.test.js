// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { initTemplateSelector } = require('./template_selector.js');

const LIST_URL = '/api/wiki/templates/';
const CONTENT_URL = '/api/wiki/templates/1/intake/content/';

/** Build the markup a create form renders: selector, textarea, announce checkbox. */
function buildForm() {
  document.body.innerHTML = `
    <form>
      <div data-template-selector
           data-template-list-url="${LIST_URL}"
           data-record-type="problem">
        <select><option value="">No template</option></select>
      </div>
      <textarea data-text-textarea></textarea>
      <input type="checkbox" name="announce" checked>
    </form>
  `;
  return {
    container: document.querySelector('[data-template-selector]'),
    select: document.querySelector('select'),
    checkbox: document.querySelector('input[name="announce"]'),
  };
}

/** Respond to the list call with one template, and to the content call with `content`.
 *
 * The content URL is a *prefix match* of the list URL, so dispatch on the exact
 * content URL first — getting this backwards makes every assertion vacuous.
 */
function stubFetch(content) {
  return vi.fn((url) => {
    const body =
      url === CONTENT_URL
        ? content
        : { templates: [{ label: 'Intake', page_title: 'Wiki', content_url: CONTENT_URL }] };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
}

/** Let the selector's chained fetch/json promises settle. */
async function flush() {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('template selector: Discord announcement', () => {
  let form;

  beforeEach(() => {
    form = buildForm();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });

  async function choose(content) {
    vi.stubGlobal('fetch', stubFetch(content));
    initTemplateSelector(form.container);
    await flush();
    form.select.value = CONTENT_URL;
    // Guard against a silently-empty dropdown making the assertions vacuous.
    expect(form.select.value).toBe(CONTENT_URL);
    form.select.dispatchEvent(new Event('change'));
    await flush();
  }

  it('unticks the announce box for a template marked announce="no"', async () => {
    await choose({ content: '- [ ] check the fuses', announce: false });

    expect(form.checkbox.checked).toBe(false);
  });

  it('ticks the announce box for an ordinary template', async () => {
    form.checkbox.checked = false;

    await choose({ content: '- [ ] check the fuses', announce: true });

    expect(form.checkbox.checked).toBe(true);
  });

  it('treats a response without an announce field as announceable', async () => {
    form.checkbox.checked = false;

    await choose({ content: '- [ ] check the fuses' });

    expect(form.checkbox.checked).toBe(true);
  });

  it('restores the announce box when the template is cleared', async () => {
    await choose({ content: '- [ ] check the fuses', announce: false });
    expect(form.checkbox.checked).toBe(false);

    // Clearing the textarea is what the form does before another choice; here we
    // just deselect, which is the "No template" option.
    form.select.value = '';
    form.select.dispatchEvent(new Event('change'));
    await flush();

    expect(form.checkbox.checked).toBe(true);
  });
});
