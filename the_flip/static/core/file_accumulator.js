/**
 * File accumulator for form-based multi-file uploads.
 *
 * Unlike native file inputs which replace files on each selection,
 * this component accumulates files across multiple selections.
 *
 * Auto-initializes on DOMContentLoaded for elements with [data-file-accumulator].
 *
 * Expected DOM structure:
 *   <div data-file-accumulator>
 *     <input type="file" data-file-input multiple>
 *     <a href="#" data-file-trigger>Add photos and videos</a>
 *     <div data-file-preview></div>
 *   </div>
 *
 * The component:
 * - Accumulates files across multiple selections
 * - Prevents duplicates (by name + size + lastModified)
 * - Renders preview pills with remove buttons
 * - Syncs accumulated files back to the input via DataTransfer API
 */

(function () {
  'use strict';

  /**
   * Check if two files are duplicates.
   * @param {File} a - First file
   * @param {File} b - Second file
   * @returns {boolean} True if files appear to be the same
   */
  function isDuplicate(a, b) {
    return a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;
  }

  /**
   * Sync accumulated files to the file input using DataTransfer API.
   * @param {HTMLInputElement} input - The file input element
   * @param {File[]} files - Array of accumulated files
   */
  function syncFilesToInput(input, files) {
    const dt = new DataTransfer();
    files.forEach((file) => dt.items.add(file));
    input.files = dt.files;
  }

  /**
   * Create a preview pill element for a file.
   * @param {File} file - The file to preview
   * @param {number} index - Index in the files array
   * @param {Function} onRemove - Callback when remove button is clicked
   * @returns {HTMLElement} The preview pill element
   */
  function createPreviewPill(file, index, onRemove) {
    const isVideo = file.type && file.type.startsWith('video/');
    const icon = isVideo ? 'fa-video' : 'fa-image';

    const pill = document.createElement('span');
    pill.className = 'pill pill--neutral pill--removable';
    pill.dataset.fileIndex = index;

    const iconEl = document.createElement('i');
    iconEl.className = `fa-solid ${icon} meta`;

    const nameEl = document.createElement('span');
    nameEl.className = 'pill__filename';
    nameEl.textContent = file.name;

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'pill__remove';
    removeBtn.setAttribute('aria-label', `Remove ${file.name}`);
    removeBtn.innerHTML = '&times;';
    removeBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      onRemove(index);
    });

    pill.appendChild(iconEl);
    pill.appendChild(nameEl);
    pill.appendChild(removeBtn);

    return pill;
  }

  /**
   * Render all preview pills.
   * @param {HTMLElement} container - The preview container
   * @param {File[]} files - Array of accumulated files
   * @param {Function} onRemove - Callback when remove button is clicked
   */
  function renderPreviews(container, files, onRemove) {
    container.innerHTML = '';
    files.forEach((file, index) => {
      container.appendChild(createPreviewPill(file, index, onRemove));
    });
  }

  /**
   * Initialize a file accumulator instance.
   * @param {HTMLElement} container - The [data-file-accumulator] element
   */
  function initFileAccumulator(container) {
    // Prevent double-initialization (e.g., in SPA contexts or dynamic DOM updates)
    if (container.dataset.fileAccumulatorInitialized) {
      return;
    }
    container.dataset.fileAccumulatorInitialized = 'true';

    const fileInput = container.querySelector('[data-file-input]');
    const trigger = container.querySelector('[data-file-trigger]');
    const previewContainer = container.querySelector('[data-file-preview]');

    if (!fileInput || !trigger || !previewContainer) {
      console.warn('File accumulator: Required elements not found', container);
      return;
    }

    let accumulatedFiles = [];

    /**
     * Remove a file by index and re-render.
     * @param {number} index - Index of file to remove
     */
    function removeFile(index) {
      accumulatedFiles.splice(index, 1);
      syncFilesToInput(fileInput, accumulatedFiles);
      renderPreviews(previewContainer, accumulatedFiles, removeFile);
    }

    /**
     * Add new files, filtering duplicates.
     * @param {FileList} newFiles - Files from the input
     */
    function addFiles(newFiles) {
      for (const file of newFiles) {
        // Check for duplicates
        const isDuplicateFile = accumulatedFiles.some((existing) => isDuplicate(existing, file));
        if (!isDuplicateFile) {
          accumulatedFiles.push(file);
        }
      }

      syncFilesToInput(fileInput, accumulatedFiles);
      renderPreviews(previewContainer, accumulatedFiles, removeFile);
    }

    // Trigger file picker when link is clicked
    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      fileInput.click();
    });

    // Handle file selection
    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files.length > 0) {
        addFiles(fileInput.files);
      }
    });
  }

  // Auto-initialize on DOMContentLoaded
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-file-accumulator]').forEach(initFileAccumulator);
  });
})();
