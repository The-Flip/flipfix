/**
 * Media grid upload and management functionality.
 *
 * Auto-initializes on DOMContentLoaded for all elements with [data-media-card].
 * Requires CSRF_TOKEN to be set globally or passed via data attribute.
 *
 * Expected DOM structure (from media_card_editable.html partial):
 *   <div data-media-card>
 *     <button data-media-upload-btn>Upload Photos</button>
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
 */

(function () {
  'use strict';

  /**
   * Initialize a single media card.
   * @param {HTMLElement} card - The [data-media-card] element
   */
  function initMediaCard(card) {
    const uploadButton = card.querySelector('[data-media-upload-btn]');
    const fileInput = card.querySelector('[data-media-file-input]');
    const container = card.querySelector('[data-media-container]');

    if (!uploadButton || !fileInput || !container) {
      console.warn('Media card: Required elements not found', card);
      return;
    }

    const altText = card.dataset.altText || 'Photo';

    // Update button text if there are existing media items
    const existingMediaCount = container.querySelectorAll('.media-grid__item').length;
    if (existingMediaCount > 0) {
      uploadButton.textContent = 'Upload More Photos';
    }

    // Trigger file picker when upload button is clicked
    uploadButton.addEventListener('click', () => fileInput.click());

    // Handle file selection
    fileInput.addEventListener('change', async (e) => {
      if (!e.target.files || !e.target.files.length) return;

      const files = Array.from(e.target.files);
      const noMediaMessage = container.querySelector('[data-no-media-message]');
      if (noMediaMessage) noMediaMessage.remove();

      for (const file of files) {
        await uploadFile(file, container, uploadButton, altText);
      }

      // Reset input to allow re-selecting the same file
      e.target.value = '';
    });

    // Attach delete handlers to existing media items
    container.querySelectorAll('.media-grid__delete').forEach((btn) => {
      attachDeleteHandler(btn, container);
    });
  }

  /**
   * Get CSRF token from global variable or cookie.
   * @returns {string} The CSRF token
   */
  function getCsrfToken() {
    // Try global variable first (set by Django template)
    if (typeof CSRF_TOKEN !== 'undefined') {
      return CSRF_TOKEN;
    }
    // Fall back to cookie
    const cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : '';
  }

  /**
   * Upload a single file to the server.
   * @param {File} file - The file to upload
   * @param {HTMLElement} container - The media container element
   * @param {HTMLElement} uploadButton - The upload button (to update text)
   * @param {string} altText - Alt text for uploaded images
   */
  async function uploadFile(file, container, uploadButton, altText) {
    const formData = new FormData();
    formData.append('action', 'upload_media');
    formData.append('file', file);
    formData.append('csrfmiddlewaretoken', getCsrfToken());

    try {
      const response = await fetch(window.location.href, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      if (data.success) {
        const mediaItem = createMediaElement(data, altText);
        container.appendChild(mediaItem);
        attachDeleteHandler(mediaItem.querySelector('.media-grid__delete'), container);
        uploadButton.textContent = 'Upload More Photos';
      } else {
        alert('Failed to upload media: ' + (data.error || 'Unknown error'));
      }
    } catch (error) {
      console.error('Upload error:', error);
      alert('Failed to upload media');
    }
  }

  /**
   * Create a media item DOM element from upload response data.
   * @param {Object} data - Response data from upload
   * @param {string} altText - Alt text for images
   * @returns {HTMLElement} The created media item element
   */
  function createMediaElement(data, altText) {
    const mediaItem = document.createElement('div');
    mediaItem.className = 'media-grid__item';
    mediaItem.dataset.mediaId = data.media_id;

    let content = '';
    if (data.media_type === 'video') {
      if (data.transcode_status === 'ready' && data.media_url) {
        const posterAttr = data.poster_url ? ` poster="${data.poster_url}"` : '';
        content = `
          <video controls${posterAttr}>
            <source src="${data.media_url}" type="video/mp4">
            Your browser doesn't support video playback.
          </video>
        `;
      } else if (data.transcode_status === 'failed') {
        content = `<div class="media-grid__status media-grid__status--error">Video processing failed.</div>`;
      } else {
        content = `<div class="media-grid__status">Processing video…</div>`;
      }
    } else {
      content = `
        <a href="${data.media_url}" target="_blank">
          <img src="${data.thumbnail_url}" alt="${altText}">
        </a>
      `;
    }

    mediaItem.innerHTML = `
      ${content}
      <button type="button" class="media-grid__delete" data-media-id="${data.media_id}" aria-label="Delete media">×</button>
    `;

    return mediaItem;
  }

  /**
   * Attach a click handler to a delete button.
   * @param {HTMLElement} button - The delete button element
   * @param {HTMLElement} container - The media container (to check if empty after delete)
   */
  function attachDeleteHandler(button, container) {
    if (!button) return;

    button.addEventListener('click', async () => {
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

          // Update upload button text if no more media
          const card = container.closest('[data-media-card]');
          if (card) {
            const remaining = container.querySelectorAll('.media-grid__item').length;
            const uploadBtn = card.querySelector('[data-media-upload-btn]');
            if (uploadBtn && remaining === 0) {
              uploadBtn.textContent = 'Upload Photos';
            }
          }
        } else {
          alert('Failed to delete media');
        }
      } catch (error) {
        console.error('Delete error:', error);
        alert('Failed to delete media');
      }
    });
  }

  // Auto-initialize on DOMContentLoaded
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-media-card]').forEach(initMediaCard);
  });

  // Export for manual initialization if needed
  window.initMediaCard = initMediaCard;
})();
