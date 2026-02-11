/**
 * Media grid upload and management functionality.
 *
 * Auto-initializes on DOMContentLoaded for all elements with [data-media-card].
 * Requires core.js (for getCsrfToken).
 *
 * Events:
 * - Dispatches 'media:uploaded' on document when video uploads complete (for polling)
 * - Listens for 'media:ready' to re-attach delete handlers after transcoding
 *
 * Expected DOM structure (from media_card_editable.html partial):
 *   <div data-media-card>
 *     <button data-media-upload-btn>Upload</button>
 *     <div data-media-container class="media-grid">
 *       <div class="media-grid__item" data-media-id="123">
 *         ...
 *         <button class="media-grid__delete" data-media-id="123">×</button>
 *       </div>
 *       <p data-no-media-message>No media.</p>
 *     </div>
 *     <input type="file" data-media-file-input multiple hidden>
 *   </div>
 *
 * Alt text for uploaded images is read from data-alt-text on the card.
 * Model name for video polling is read from data-model-name on the card.
 */

(function () {
  'use strict';

  /**
   * Get required card elements or null if missing.
   * @param {HTMLElement} card - The media card element
   * @returns {Object|null} Object with uploadButton, fileInput, container or null
   */
  function getCardElements(card) {
    const uploadButton = card.querySelector('[data-media-upload-btn]');
    const fileInput = card.querySelector('[data-media-file-input]');
    const container = card.querySelector('[data-media-container]');

    if (!uploadButton || !fileInput || !container) {
      console.warn('Media card: Required elements not found', card);
      return null;
    }

    return { uploadButton, fileInput, container };
  }

  /**
   * Get card configuration from data attributes.
   * @param {HTMLElement} card - The media card element
   * @returns {Object} Object with altText and modelName
   */
  function getCardConfig(card) {
    return {
      altText: card.dataset.altText || 'Photo',
      modelName: card.dataset.modelName || 'LogEntryMedia',
    };
  }

  /**
   * Handle file upload for multiple files.
   * @param {FileList} files - Files to upload
   * @param {Object} elements - Card elements (uploadButton, fileInput, container)
   * @param {Object} config - Card config (altText, modelName)
   */
  async function handleFileUpload(files, elements, config) {
    const { uploadButton, container } = elements;
    const { altText, modelName } = config;
    const total = files.length;
    let completed = 0;
    let hasVideo = false;

    const noMediaMessage = container.querySelector('[data-no-media-message]');
    if (noMediaMessage) noMediaMessage.remove();

    uploadButton.disabled = true;
    uploadButton.textContent = `Uploading 1 of ${total}...`;

    for (const file of files) {
      const result = await uploadFile(file, container, uploadButton, altText, modelName);
      completed++;

      if (completed < total) {
        uploadButton.textContent = `Uploading ${completed + 1} of ${total}...`;
      }

      if (result && result.media_type === 'video') {
        hasVideo = true;
      }
    }

    uploadButton.disabled = false;
    uploadButton.textContent = 'Upload More';

    if (hasVideo) {
      document.dispatchEvent(
        new CustomEvent('media:uploaded', {
          detail: { hasVideo: true },
        })
      );
    }
  }

  /**
   * Initialize a single media card.
   * @param {HTMLElement} card - The [data-media-card] element
   */
  function initMediaCard(card) {
    const elements = getCardElements(card);
    if (!elements) return;

    const { uploadButton, fileInput, container } = elements;
    const config = getCardConfig(card);

    // Update button text if there are existing media items
    const existingMediaCount = container.querySelectorAll('.media-grid__item').length;
    if (existingMediaCount > 0) {
      uploadButton.textContent = 'Upload More';
    }

    // Trigger file picker when upload button is clicked
    uploadButton.addEventListener('click', () => fileInput.click());

    // Handle file selection
    fileInput.addEventListener('change', async (e) => {
      if (!e.target.files || !e.target.files.length) return;

      await handleFileUpload(Array.from(e.target.files), elements, config);
      e.target.value = '';
    });

    // Attach delete handlers to existing media items
    container.querySelectorAll('.media-grid__delete').forEach((btn) => {
      attachDeleteHandler(btn, container);
    });

    // Listen for media:ready events to re-attach delete handlers after transcoding
    card.addEventListener('media:ready', (e) => {
      const newDeleteBtn = e.detail.container.querySelector('.media-grid__delete');
      if (newDeleteBtn) {
        attachDeleteHandler(newDeleteBtn, container);
      }
    });
  }

  /**
   * Upload a single file to the server.
   * @param {File} file - The file to upload
   * @param {HTMLElement} container - The media container element
   * @param {HTMLElement} uploadButton - The upload button (to update text)
   * @param {string} altText - Alt text for uploaded images
   * @param {string} modelName - Model name for video polling
   * @returns {Object|null} Response data on success, null on failure
   */
  async function uploadFile(file, container, uploadButton, altText, modelName) {
    const formData = new FormData();
    formData.append('action', 'upload_media');
    formData.append('media_file', file);
    formData.append('csrfmiddlewaretoken', getCsrfToken());

    try {
      const response = await fetch(window.location.href, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      if (data.success) {
        const mediaItem = createMediaElement(data, altText, modelName);
        container.appendChild(mediaItem);
        attachDeleteHandler(mediaItem.querySelector('.media-grid__delete'), container);
        uploadButton.textContent = 'Upload More';
        return data;
      } else {
        console.error('Upload failed:', data.error || 'Unknown error');
        return null;
      }
    } catch (error) {
      console.error('Upload error:', error);
      return null;
    }
  }

  /**
   * Build video content HTML based on transcode status.
   * @param {Object} data - Upload response data
   * @param {string} modelName - Model name for polling
   * @returns {string} HTML string
   */
  function buildVideoContent(data, modelName) {
    if (data.transcode_status === 'ready' && data.media_url) {
      const posterAttr = data.poster_url ? ` poster="${data.poster_url}"` : '';
      return `
        <video controls${posterAttr}>
          <source src="${data.media_url}" type="video/mp4">
          Your browser doesn't support video playback.
        </video>
      `;
    } else if (data.transcode_status === 'failed') {
      return `<div class="media-grid__status media-grid__status--error">Video processing failed.</div>`;
    } else {
      return `<div class="media-grid__status" data-media-poll-id="${data.media_id}" data-media-poll-model="${modelName}">Processing video...</div>`;
    }
  }

  /**
   * Build image content HTML.
   * @param {Object} data - Upload response data
   * @param {string} altText - Alt text for image
   * @returns {string} HTML string
   */
  function buildImageContent(data, altText) {
    return `
      <a href="${data.media_url}" target="_blank">
        <img src="${data.thumbnail_url}" alt="${altText}">
      </a>
    `;
  }

  /**
   * Create a media item DOM element from upload response data.
   * @param {Object} data - Response data from upload
   * @param {string} altText - Alt text for images
   * @param {string} modelName - Model name for video polling
   * @returns {HTMLElement} The created media item element
   */
  function createMediaElement(data, altText, modelName) {
    const mediaItem = document.createElement('div');
    mediaItem.className = 'media-grid__item';
    mediaItem.dataset.mediaId = data.media_id;

    const content =
      data.media_type === 'video'
        ? buildVideoContent(data, modelName)
        : buildImageContent(data, altText);

    mediaItem.innerHTML = `
      ${content}
      <button type="button" class="media-grid__delete" data-media-id="${data.media_id}" aria-label="Delete media">&times;</button>
    `;

    return mediaItem;
  }

  /**
   * Update upload button text based on remaining media count.
   * @param {HTMLElement} container - The media container
   */
  function updateButtonTextAfterDelete(container) {
    const card = container.closest('[data-media-card]');
    if (card) {
      const remaining = container.querySelectorAll('.media-grid__item').length;
      const uploadBtn = card.querySelector('[data-media-upload-btn]');
      if (uploadBtn && remaining === 0) {
        uploadBtn.textContent = 'Upload';
      }
    }
  }

  /**
   * Attach a click handler to a delete button.
   * @param {HTMLElement} button - The delete button element
   * @param {HTMLElement} container - The media container (to check if empty after delete)
   */
  function attachDeleteHandler(button, container) {
    if (!button) return;

    button.addEventListener('click', async () => {
      if (!confirm('Delete?')) {
        return;
      }

      const mediaId = button.dataset.mediaId;

      const formData = new FormData();
      formData.append('action', 'delete_media');
      formData.append('media_id', mediaId);
      formData.append('csrfmiddlewaretoken', getCsrfToken());

      try {
        const response = await fetch(window.location.href, {
          method: 'POST',
          body: formData,
        });

        if (response.ok) {
          const mediaItem = button.closest('.media-grid__item');
          mediaItem.remove();
          updateButtonTextAfterDelete(container);
        } else {
          console.error('Delete failed: Server returned', response.status);
        }
      } catch (error) {
        console.error('Delete error:', error);
      }
    });
  }

  // Auto-initialize on DOMContentLoaded
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-media-card]').forEach(initMediaCard);
  });
})();
