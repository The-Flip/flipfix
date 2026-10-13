// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { applyTextareaEdit, escapeHtml } = require('./core.js');
const { initImageUpload } = require('./markdown_image_upload.js');

const UPLOAD_URL = '/api/wiki/media/';
const MARKDOWN = '![photo](/wiki/media/42/)';

function buildForm() {
  document.body.innerHTML = `
    <form>
      <textarea id="id_content"
                data-image-upload-url="${UPLOAD_URL}"
                data-image-upload-page="7">Intro</textarea>
      <button type="button" data-image-upload-button="id_content">Add image</button>
      <input type="file" class="hidden" data-image-upload-input="id_content">
    </form>
  `;
  const textarea = document.querySelector('textarea');
  initImageUpload(textarea);
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = textarea.value.length;
  return textarea;
}

function pasteFiles(textarea, files) {
  const event = new Event('paste', { bubbles: true, cancelable: true });
  event.clipboardData = { files };
  textarea.dispatchEvent(event);
  return event;
}

/** Let the upload's fetch/json promises settle. */
async function flush() {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('markdown image upload', () => {
  let showMessage;
  let resolveFetch;

  beforeEach(() => {
    showMessage = vi.fn();
    vi.stubGlobal('applyTextareaEdit', applyTextareaEdit);
    vi.stubGlobal('escapeHtml', escapeHtml);
    vi.stubGlobal('getCsrfToken', () => 'token');
    vi.stubGlobal('showMessage', showMessage);
    // jsdom doesn't implement execCommand; force the .value fallback.
    document.execCommand = () => false;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise((resolve) => {
            resolveFetch = resolve;
          })
      )
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });

  it('shows a placeholder, then swaps in the uploaded image markdown', async () => {
    const textarea = buildForm();
    const file = new File(['x'], 'photo.png', { type: 'image/png' });

    const event = pasteFiles(textarea, [file]);

    expect(event.defaultPrevented).toBe(true);
    expect(textarea.value).toMatch(/^Intro\n!\[Uploading photo\.png…\]\(uploading-[\w-]+\)$/);

    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe(UPLOAD_URL);
    expect(options.headers['X-CSRFToken']).toBe('token');
    expect(options.body.get('file').name).toBe('photo.png');
    expect(options.body.get('page')).toBe('7');

    resolveFetch({
      ok: true,
      json: () => Promise.resolve({ success: true, markdown: MARKDOWN }),
    });
    await flush();

    expect(textarea.value).toBe(`Intro\n${MARKDOWN}`);
    const selected = textarea.value.substring(textarea.selectionStart, textarea.selectionEnd);
    expect(selected).toBe('photo');
  });

  it('removes the placeholder and reports the error when the upload fails', async () => {
    const textarea = buildForm();
    pasteFiles(textarea, [new File(['x'], '<b>.png', { type: 'image/png' })]);

    resolveFetch({
      ok: false,
      json: () => Promise.resolve({ success: false, error: 'Upload a valid image.' }),
    });
    await flush();

    expect(textarea.value).toBe('Intro');
    expect(showMessage).toHaveBeenCalledWith(
      'error',
      "Couldn't add &lt;b&gt;.png: Upload a valid image."
    );
  });

  it('blocks saving while an upload is in flight, and allows it once done', async () => {
    const textarea = buildForm();
    const form = textarea.form;
    pasteFiles(textarea, [new File(['x'], 'photo.png', { type: 'image/png' })]);

    const blocked = new Event('submit', { cancelable: true });
    form.dispatchEvent(blocked);
    expect(blocked.defaultPrevented).toBe(true);
    expect(showMessage).toHaveBeenCalledWith('warning', expect.stringContaining('still uploading'));

    resolveFetch({ ok: true, json: () => Promise.resolve({ success: true, markdown: MARKDOWN }) });
    await flush();

    const allowed = new Event('submit', { cancelable: true });
    form.dispatchEvent(allowed);
    expect(allowed.defaultPrevented).toBe(false);
  });

  it('allows saving again after a failed upload', async () => {
    const textarea = buildForm();
    pasteFiles(textarea, [new File(['x'], 'photo.png', { type: 'image/png' })]);
    resolveFetch({ ok: false, json: () => Promise.reject(new Error('not json')) });
    await flush();

    expect(showMessage).toHaveBeenCalledWith(
      'error',
      "Couldn't add photo.png: Upload failed. Please try again."
    );
    const submit = new Event('submit', { cancelable: true });
    textarea.form.dispatchEvent(submit);
    expect(submit.defaultPrevented).toBe(false);
  });

  it('leaves non-image pastes to the browser', () => {
    const textarea = buildForm();
    const event = pasteFiles(textarea, [new File(['x'], 'notes.txt', { type: 'text/plain' })]);

    expect(event.defaultPrevented).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('uploads any file chosen in the picker, so the server can reject it with a message', () => {
    const textarea = buildForm();
    const input = document.querySelector('[data-image-upload-input]');
    const file = new File(['x'], 'notes.txt', { type: 'text/plain' });
    Object.defineProperty(input, 'files', { value: [file] });

    input.dispatchEvent(new Event('change'));

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(textarea.value).toContain('Uploading notes.txt');
  });

  it('opens the file picker from the Add image button', () => {
    buildForm();
    const input = document.querySelector('[data-image-upload-input]');
    const click = vi.spyOn(input, 'click');

    document.querySelector('[data-image-upload-button]').click();

    expect(click).toHaveBeenCalled();
  });
});
