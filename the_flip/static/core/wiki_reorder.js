(function () {
  'use strict';

  function initReorder(container) {
    const saveUrl = container.dataset.saveUrl;

    // Initialize SortableJS on all page lists
    container.querySelectorAll('[data-sortable-group="pages"]').forEach((list) => {
      new Sortable(list, {
        handle: '.reorder-list__handle',
        animation: 150,
        ghostClass: 'reorder-list__item--ghost',
        chosenClass: 'reorder-list__item--chosen',
        dragClass: 'reorder-list__item--drag',
        onSort: () => {
          savePageOrder(list, saveUrl);
        },
      });
    });

    // Initialize SortableJS on all tag containers
    container.querySelectorAll('[data-sortable-group="tags"]').forEach((tagContainer) => {
      new Sortable(tagContainer, {
        handle: '.reorder-folder__header > .reorder-list__handle',
        animation: 150,
        ghostClass: 'reorder-folder--ghost',
        chosenClass: 'reorder-folder--chosen',
        dragClass: 'reorder-folder--drag',
        draggable: '.reorder-folder',
        onSort: () => {
          saveTagOrder(tagContainer, saveUrl);
        },
      });
    });
  }

  function savePageOrder(list, saveUrl) {
    const tag = list.dataset.tag;
    const pages = [];
    list.querySelectorAll('.reorder-list__item').forEach((item, index) => {
      pages.push({
        tag: tag,
        slug: item.dataset.slug,
        order: index,
      });
    });

    postOrder(saveUrl, { pages: pages, tags: [] });
  }

  function saveTagOrder(tagContainer, saveUrl) {
    const tags = [];
    const folders = tagContainer.querySelectorAll(':scope > .reorder-folder');
    folders.forEach((folder, index) => {
      tags.push({
        tag: folder.dataset.tagPath,
        order: index,
      });
    });

    postOrder(saveUrl, { pages: [], tags: tags });
  }

  async function postOrder(saveUrl, payload) {
    document.dispatchEvent(new CustomEvent('save:start'));

    try {
      const res = await fetch(saveUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Save failed');
      const data = await res.json();
      document.dispatchEvent(
        new CustomEvent('save:end', { detail: { ok: data.status === 'success' } })
      );
    } catch {
      document.dispatchEvent(new CustomEvent('save:end', { detail: { ok: false } }));
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const container = document.querySelector('[data-reorder-tree]');
    if (container) initReorder(container);
  });
})();
