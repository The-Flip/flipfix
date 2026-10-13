/**
 * Markdown Image Upload Module
 *
 * Lets authors add images to a markdown textarea by pasting, dragging and
 * dropping, or choosing a file. Each image uploads in the background and an
 * `![alt](url)` reference is inserted where the cursor was.
 *
 * Auto-initializes on textareas with [data-image-upload-url]:
 *   - data-image-upload-url: endpoint that accepts POST `file` (and
 *     optional `page`) and returns { success, markdown } or { success, error }
 *   - data-image-upload-page: optional record id sent as `page`
 *
 * Optional file-picker controls, linked to the textarea by id:
 *   <button type="button" data-image-upload-button="<textarea id>">
 *   <input type="file" class="hidden" data-image-upload-input="<textarea id>">
 *
 * While uploading, a placeholder like `![Uploading photo.jpg…](uploading-3)`
 * marks the spot. It is found again by its unique token, not by position, so
 * typing elsewhere during the upload is safe. Submitting the textarea's form
 * is blocked (with a message) while any upload is still in flight.
 *
 * Requires core.js (for applyTextareaEdit, getCsrfToken, showMessage, escapeHtml).
 */
(function (exports) {
  'use strict';

  // ── Pure Functions ─────────────────────────────────────────────
  //
  // Each edit function returns a replacement descriptor for
  // applyTextareaEdit(), or null when there's nothing to do:
  //   { replaceStart, replaceEnd, replacement, selectionStart, selectionEnd }

  /**
   * Build the placeholder text shown while an image uploads.
   *
   * @param {string} filename - name of the file being uploaded
   * @param {string} token - unique id for this upload
   * @returns {string}
   */
  function makePlaceholder(filename, token) {
    const safeName = filename.replace(/[[\]]/g, '');
    return `![Uploading ${safeName}…](uploading-${token})`;
  }

  /**
   * Insert a placeholder on its own line, after the line holding the cursor.
   *
   * Existing text is never replaced or split: right after an upload the
   * previous image's alt text is selected, and adding another image straight
   * away must not land inside it. On an empty line the placeholder goes on
   * that line.
   *
   * @param {string} value - textarea content
   * @param {number} end - selection end (the cursor)
   * @param {string} placeholder - text from makePlaceholder()
   * @returns {object} replacement descriptor; cursor lands after the placeholder.
   *   Its `replacement` (placeholder plus any added newline) is what
   *   removePlaceholder() should remove if the upload fails.
   */
  function insertPlaceholder(value, end, placeholder) {
    const newline = value.indexOf('\n', end);
    const lineEnd = newline === -1 ? value.length : newline;
    const lineStart = end === 0 ? 0 : value.lastIndexOf('\n', end - 1) + 1;
    const replacement = lineStart === lineEnd ? placeholder : `\n${placeholder}`;
    const cursor = lineEnd + replacement.length;
    return {
      replaceStart: lineEnd,
      replaceEnd: lineEnd,
      replacement,
      selectionStart: cursor,
      selectionEnd: cursor,
    };
  }

  /**
   * Shift a selection offset to account for replacing [at, at + oldLength)
   * with text of newLength.
   */
  function shiftOffset(offset, at, oldLength, newLength) {
    if (offset <= at) return offset;
    if (offset >= at + oldLength) return offset + newLength - oldLength;
    return at + newLength; // inside the replaced text: move to its end
  }

  /**
   * Replace a placeholder with the uploaded image's markdown.
   *
   * If the cursor is still right after the placeholder (the author hasn't
   * moved on), the alt text is selected so it can be typed over. Otherwise
   * the author's selection is kept where it was.
   *
   * @param {string} value - textarea content
   * @param {string} placeholder - text from makePlaceholder()
   * @param {string} markdown - image markdown from the server
   * @param {number} selStart - current selection start
   * @param {number} selEnd - current selection end
   * @returns {object|null} replacement descriptor, or null if the placeholder is gone
   */
  function replacePlaceholder(value, placeholder, markdown, selStart, selEnd) {
    const at = value.indexOf(placeholder);
    if (at === -1) return null;

    const placeholderEnd = at + placeholder.length;
    const cursorAfterPlaceholder = selStart === placeholderEnd && selEnd === placeholderEnd;
    const altEnd = markdown.indexOf('](');

    let selectionStart;
    let selectionEnd;
    if (cursorAfterPlaceholder && markdown.startsWith('![') && altEnd !== -1) {
      selectionStart = at + 2;
      selectionEnd = at + altEnd;
    } else {
      selectionStart = shiftOffset(selStart, at, placeholder.length, markdown.length);
      selectionEnd = shiftOffset(selEnd, at, placeholder.length, markdown.length);
    }

    return {
      replaceStart: at,
      replaceEnd: placeholderEnd,
      replacement: markdown,
      selectionStart,
      selectionEnd,
    };
  }

  /**
   * Remove placeholder text (after a failed upload), keeping the author's selection.
   *
   * @param {string} value - textarea content
   * @param {string} placeholder - text to remove: the inserted text including
   *   its added newline, or just the makePlaceholder() text
   * @param {number} selStart - current selection start
   * @param {number} selEnd - current selection end
   * @returns {object|null} replacement descriptor, or null if the placeholder is gone
   */
  function removePlaceholder(value, placeholder, selStart, selEnd) {
    const at = value.indexOf(placeholder);
    if (at === -1) return null;
    return {
      replaceStart: at,
      replaceEnd: at + placeholder.length,
      replacement: '',
      selectionStart: shiftOffset(selStart, at, placeholder.length, 0),
      selectionEnd: shiftOffset(selEnd, at, placeholder.length, 0),
    };
  }

  /**
   * Pick the likely images out of a FileList-like collection.
   *
   * Files with no MIME type are kept: some browsers report none for HEIC/HEIF
   * photos. The server validates every upload, so a non-image that slips
   * through gets a clear error rather than being silently ignored.
   *
   * @param {Iterable<File>} files
   * @returns {File[]}
   */
  function imageFiles(files) {
    return Array.from(files || []).filter(
      (file) => file.type === '' || file.type.startsWith('image/')
    );
  }

  // ── DOM Wiring ────────────────────────────────────────────────

  let uploadCounter = 0;

  /** In-flight uploads per textarea, so the form isn't saved with a placeholder in it. */
  const pendingUploads = new WeakMap();

  function changePending(textarea, delta) {
    pendingUploads.set(textarea, (pendingUploads.get(textarea) ?? 0) + delta);
  }

  async function postImage(textarea, file) {
    const formData = new FormData();
    formData.append('file', file);
    const page = textarea.dataset.imageUploadPage;
    if (page) formData.append('page', page);

    const response = await fetch(textarea.dataset.imageUploadUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
      body: formData,
    });
    let data = null;
    try {
      data = await response.json();
    } catch {
      // Non-JSON error page (e.g. 413 from a proxy); handled below.
    }
    if (!response.ok || !data?.success) {
      throw new Error(data?.error || 'Upload failed. Please try again.');
    }
    return data.markdown;
  }

  async function uploadFile(textarea, file) {
    uploadCounter += 1;
    const placeholder = makePlaceholder(file.name, `${Date.now()}-${uploadCounter}`);
    const insertion = insertPlaceholder(textarea.value, textarea.selectionEnd, placeholder);
    applyTextareaEdit(textarea, insertion);
    changePending(textarea, 1);

    try {
      const markdown = await postImage(textarea, file);
      applyTextareaEdit(
        textarea,
        replacePlaceholder(
          textarea.value,
          placeholder,
          markdown,
          textarea.selectionStart,
          textarea.selectionEnd
        )
      );
    } catch (err) {
      const { value, selectionStart, selectionEnd } = textarea;
      // Remove the newline added before the placeholder too, unless the
      // author has typed right next to it since.
      applyTextareaEdit(
        textarea,
        removePlaceholder(value, insertion.replacement, selectionStart, selectionEnd) ??
          removePlaceholder(value, placeholder, selectionStart, selectionEnd)
      );
      showMessage('error', escapeHtml(`Couldn't add ${file.name}: ${err.message}`));
    } finally {
      changePending(textarea, -1);
    }
  }

  /**
   * Upload each file. Callers filter first where needed: paste and drop keep
   * only likely images (anything else is left to the browser), while files
   * chosen in the picker all go to the server, so a wrong pick gets an error
   * message instead of being silently ignored.
   */
  function uploadFiles(textarea, files) {
    Array.from(files).forEach((file) => uploadFile(textarea, file));
  }

  function initImageUpload(textarea) {
    // Capture phase, so this runs before any other submit handler on the form.
    textarea.form?.addEventListener(
      'submit',
      (e) => {
        if ((pendingUploads.get(textarea) ?? 0) === 0) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        showMessage('warning', 'Images are still uploading. Save again once they finish.');
      },
      true
    );

    textarea.addEventListener('paste', (e) => {
      const files = imageFiles(e.clipboardData?.files);
      if (files.length === 0) return;
      e.preventDefault();
      uploadFiles(textarea, files);
    });

    textarea.addEventListener('dragover', (e) => {
      if (e.dataTransfer?.types.includes('Files')) {
        e.preventDefault();
        textarea.classList.add('form-textarea--dropping');
      }
    });
    textarea.addEventListener('dragleave', () =>
      textarea.classList.remove('form-textarea--dropping')
    );
    textarea.addEventListener('drop', (e) => {
      textarea.classList.remove('form-textarea--dropping');
      const files = imageFiles(e.dataTransfer?.files);
      if (files.length === 0) return;
      e.preventDefault();
      textarea.focus();
      uploadFiles(textarea, files);
    });

    if (!textarea.id) return;
    const input = document.querySelector(`[data-image-upload-input="${textarea.id}"]`);
    const button = document.querySelector(`[data-image-upload-button="${textarea.id}"]`);
    if (!input || !button) return;

    button.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
      textarea.focus();
      uploadFiles(textarea, input.files);
      input.value = ''; // allow choosing the same file again
    });
  }

  function init() {
    document.querySelectorAll('textarea[data-image-upload-url]').forEach(initImageUpload);
  }

  // Auto-init in the browser only; tests call initImageUpload() directly.
  if (typeof document !== 'undefined' && !exports) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  // ── Test Exports (Node only) ──────────────────────────────────

  if (exports) {
    exports.makePlaceholder = makePlaceholder;
    exports.insertPlaceholder = insertPlaceholder;
    exports.replacePlaceholder = replacePlaceholder;
    exports.removePlaceholder = removePlaceholder;
    exports.imageFiles = imageFiles;
    exports.initImageUpload = initImageUpload;
  }
})(typeof module !== 'undefined' ? module.exports : null);
