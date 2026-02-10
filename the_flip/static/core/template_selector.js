/**
 * Template Selector
 *
 * Provides a dropdown to select a wiki template for pre-filling create forms.
 * Auto-discovers configuration from data attributes on [data-template-selector].
 *
 * Works across all create forms: problem reports, log entries, part requests,
 * and wiki pages. Hides itself when no templates match the current filters.
 *
 * Data attributes on the container:
 *   data-template-selector     - marker for auto-init
 *   data-template-list-url     - API endpoint for listing templates
 *   data-record-type           - "problem", "log", "partrequest", "page"
 *   data-machine-slug          - current machine slug (optional)
 *   data-location-slug         - current location slug (optional)
 *
 * Listens for:
 *   machine:changed (on form) - updates machine/location and refetches
 *   change (on priority select) - refetches with new priority
 */

function initTemplateSelector(container) {
  const select = container.querySelector('select');
  const listUrl = container.dataset.templateListUrl;
  const recordType = container.dataset.recordType;

  if (!select || !listUrl || !recordType) return;

  const form = container.closest('form');
  if (!form) return;

  const textarea = form.querySelector('[data-text-textarea]');
  if (!textarea) return;

  let machineSlug = container.dataset.machineSlug || '';
  let locationSlug = container.dataset.locationSlug || '';
  let lastTemplateContent = null;
  let locked = false;
  let preselectUrl = container.dataset.preselectUrl || '';

  // Find priority select (problem reports only)
  const prioritySelect = form.querySelector('select[name="priority"]');

  // ---------------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------------

  function buildListUrl() {
    const params = new URLSearchParams({ record_type: recordType });
    if (machineSlug) params.set('machine_slug', machineSlug);
    if (locationSlug) params.set('location_slug', locationSlug);
    if (prioritySelect && prioritySelect.value) {
      params.set('priority', prioritySelect.value);
    }
    return `${listUrl}?${params}`;
  }

  function fetchTemplates() {
    fetch(buildListUrl())
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => renderOptions(data.templates || []))
      .catch(() => renderOptions([]));
  }

  function renderOptions(templates) {
    // Clear existing options except the blank placeholder
    while (select.options.length > 1) {
      select.remove(1);
    }

    templates.forEach((t) => {
      const option = document.createElement('option');
      option.value = t.content_url;
      option.textContent = `${t.label} (${t.page_title})`;
      select.appendChild(option);
    });

    // Auto-select if a preselect URL was provided (button-click flow).
    // Content is already in the textarea from session prefill — just sync
    // the dropdown's visual state and the lock tracking variable.
    if (preselectUrl) {
      for (const option of select.options) {
        if (option.value === preselectUrl) {
          select.value = preselectUrl;
          lastTemplateContent = textarea.value;
          break;
        }
      }
      preselectUrl = ''; // Only preselect once
    }

    // Don't toggle visibility while user is editing template content —
    // the lock hint must stay visible.
    if (locked) return;

    // Show/hide the entire container
    if (templates.length > 0) {
      container.classList.remove('hidden');
    } else {
      container.classList.add('hidden');
    }
  }

  // ---------------------------------------------------------------------------
  // Template selection
  // ---------------------------------------------------------------------------

  function applyContent(content) {
    textarea.value = content;
    // Store the textarea's own value — it may normalise line endings (e.g.
    // \r\n → \n), so reading it back avoids a false mismatch in the lock
    // check that would immediately disable the selector.
    lastTemplateContent = textarea.value;
    locked = false;
    select.disabled = false;
    // Dispatch input event so auto-resize and other listeners react
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function clearContent() {
    textarea.value = '';
    lastTemplateContent = null;
    locked = false;
    select.disabled = false;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  select.addEventListener('change', () => {
    const contentUrl = select.value;
    if (!contentUrl) {
      clearContent();
      clearPageFields();
      return;
    }

    fetch(contentUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => {
        applyContent(data.content || '');
        applyPageFields(data);
      })
      .catch(() => {
        /* silently fail */
      });
  });

  // ---------------------------------------------------------------------------
  // Wiki page fields (title + tags)
  // ---------------------------------------------------------------------------

  let originalTitle = null;

  function applyPageFields(data) {
    if (recordType !== 'page') return;

    // Title
    if (data.title) {
      const titleInput = form.querySelector('input[name="title"]');
      if (titleInput) {
        originalTitle = titleInput.value;
        titleInput.value = data.title;
      }
    }

    // Tags
    if (data.tags && data.tags.length) {
      const tagInput = form.querySelector('[data-tag-chip-input]');
      if (tagInput && tagInput.tagChipInput) {
        tagInput.tagChipInput.clearAll();
        data.tags.forEach((tag) => tagInput.tagChipInput.addTag(tag));
      }
    }
  }

  function clearPageFields() {
    if (recordType !== 'page') return;

    // Restore title
    if (originalTitle !== null) {
      const titleInput = form.querySelector('input[name="title"]');
      if (titleInput) titleInput.value = originalTitle;
      originalTitle = null;
    }

    // Clear tags
    const tagInput = form.querySelector('[data-tag-chip-input]');
    if (tagInput && tagInput.tagChipInput) {
      tagInput.tagChipInput.clearAll();
    }
  }

  // ---------------------------------------------------------------------------
  // Lock after user edits
  // ---------------------------------------------------------------------------

  const hintEl = document.createElement('p');
  hintEl.className = 'form-hint';
  hintEl.textContent = 'Clear the text to choose a different template.';
  hintEl.style.display = 'none';
  container.appendChild(hintEl);

  textarea.addEventListener('input', () => {
    if (lastTemplateContent === null) return;

    if (textarea.value === '') {
      // User cleared — unlock
      locked = false;
      select.disabled = false;
      select.value = '';
      lastTemplateContent = null;
      hintEl.style.display = 'none';
      container.classList.remove('hidden');
      clearPageFields();
    } else if (textarea.value !== lastTemplateContent) {
      // User edited — lock
      locked = true;
      select.disabled = true;
      hintEl.style.display = '';
      container.classList.remove('hidden');
    }
  });

  // ---------------------------------------------------------------------------
  // External events
  // ---------------------------------------------------------------------------

  // Machine changed (from machine autocomplete)
  form.addEventListener('machine:changed', (event) => {
    machineSlug = event.detail.slug || '';
    locationSlug = event.detail.locationSlug || '';
    container.dataset.machineSlug = machineSlug;
    container.dataset.locationSlug = locationSlug;
    fetchTemplates();
  });

  // Priority changed (problem reports)
  if (prioritySelect) {
    prioritySelect.addEventListener('change', () => {
      fetchTemplates();
    });
  }

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  fetchTemplates();
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-template-selector]').forEach((el) => initTemplateSelector(el));
  });
}

if (typeof module !== 'undefined') {
  module.exports = { initTemplateSelector };
}
