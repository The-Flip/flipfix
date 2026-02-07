(function () {
  'use strict';

  var statusEl;
  var fadeTimer;

  function showStatus(text, isError) {
    if (!statusEl) return;
    clearTimeout(fadeTimer);
    statusEl.textContent = text;
    statusEl.classList.toggle('reorder-page__status--error', isError);
    statusEl.classList.remove('reorder-page__status--fade');
    if (!isError) {
      fadeTimer = setTimeout(function () {
        statusEl.classList.add('reorder-page__status--fade');
      }, 1500);
    }
  }

  function initReorder(container) {
    var saveUrl = container.dataset.saveUrl;
    statusEl = document.querySelector('[data-reorder-status]');

    // Initialize SortableJS on all page lists
    container.querySelectorAll('[data-sortable-group="pages"]').forEach(function (list) {
      new Sortable(list, {
        handle: '.reorder-list__handle',
        animation: 150,
        ghostClass: 'reorder-list__item--ghost',
        chosenClass: 'reorder-list__item--chosen',
        dragClass: 'reorder-list__item--drag',
        onSort: function () {
          savePageOrder(list, saveUrl);
        },
      });
    });

    // Initialize SortableJS on all tag containers
    container.querySelectorAll('[data-sortable-group="tags"]').forEach(function (tagContainer) {
      new Sortable(tagContainer, {
        handle: '.reorder-folder__header > .reorder-list__handle',
        animation: 150,
        ghostClass: 'reorder-folder--ghost',
        chosenClass: 'reorder-folder--chosen',
        dragClass: 'reorder-folder--drag',
        draggable: '.reorder-folder',
        onSort: function () {
          saveTagOrder(tagContainer, saveUrl);
        },
      });
    });
  }

  function savePageOrder(list, saveUrl) {
    var tag = list.dataset.tag;
    var pages = [];
    list.querySelectorAll('.reorder-list__item').forEach(function (item, index) {
      pages.push({
        tag: tag,
        slug: item.dataset.slug,
        order: index,
      });
    });

    postOrder(saveUrl, { pages: pages, tags: [] });
  }

  function saveTagOrder(tagContainer, saveUrl) {
    var tags = [];
    var folders = tagContainer.querySelectorAll(':scope > .reorder-folder');
    folders.forEach(function (folder, index) {
      tags.push({
        tag: folder.dataset.tagPath,
        order: index,
      });
    });

    postOrder(saveUrl, { pages: [], tags: tags });
  }

  function postOrder(saveUrl, payload) {
    fetch(saveUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (!res.ok) throw new Error('Save failed');
        return res.json();
      })
      .then(function (data) {
        if (data.status === 'success') {
          showStatus('Saved', false);
        } else {
          showStatus('Error saving', true);
        }
      })
      .catch(function () {
        showStatus('Error saving', true);
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var container = document.querySelector('[data-reorder-tree]');
    if (container) initReorder(container);
  });
})();
