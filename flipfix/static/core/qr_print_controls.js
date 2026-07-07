/**
 * Bulk QR print controls.
 *
 * Progressive enhancement for the bulk QR print page: lets the user pick the
 * printed QR size (in decimal inches) and choose which machines to include,
 * with a live on-screen preview. With JS disabled the page still renders every
 * QR at the default size and prints all of them.
 *
 * Auto-initializes on DOMContentLoaded for elements with [data-qr-print-controls].
 *
 * Expected DOM:
 *   <div data-qr-print-controls data-qr-grid-selector=".qr-grid">
 *     <input type="number" data-qr-size-input value="2.0">
 *     <button data-qr-select-all>…</button>
 *     <button data-qr-select-none>…</button>
 *     <input type="checkbox" value="<machine-id>" data-qr-machine-toggle checked>
 *     …
 *   </div>
 *   <div class="qr-grid">
 *     <div class="qr-card" data-machine-id="<machine-id>">…</div>
 *     …
 *   </div>
 *
 * Sizing is driven by the `--qr-print-size` custom property set on the grid;
 * the stylesheet consumes it for `.qr-card__image` width/height and the grid
 * column sizing. CSS inches map to physical inches when printing.
 *
 * Selection toggles the shared `.hidden` (display:none) utility on each card,
 * which also removes hidden cards from the printed output.
 */

(function () {
  'use strict';

  function initQrPrintControls(root) {
    if (root.dataset.qrPrintControlsInitialized) {
      return;
    }
    root.dataset.qrPrintControlsInitialized = 'true';

    const grid = document.querySelector(root.dataset.qrGridSelector || '.qr-grid');
    if (!grid) {
      return;
    }

    // --- Size control -------------------------------------------------------
    const sizeInput = root.querySelector('[data-qr-size-input]');

    function applySize() {
      const inches = parseFloat(sizeInput.value);
      if (!Number.isFinite(inches) || inches <= 0) {
        return;
      }
      grid.style.setProperty('--qr-print-size', inches + 'in');
    }

    if (sizeInput) {
      sizeInput.addEventListener('input', applySize);
      applySize(); // honor the server-rendered default on load
    }

    // --- Machine selection --------------------------------------------------
    const toggles = Array.from(root.querySelectorAll('[data-qr-machine-toggle]'));
    const cardById = new Map();
    grid.querySelectorAll('[data-machine-id]').forEach((card) => {
      cardById.set(card.dataset.machineId, card);
    });

    function syncCard(toggle) {
      const card = cardById.get(toggle.value);
      if (card) {
        card.classList.toggle('hidden', !toggle.checked);
      }
    }

    toggles.forEach((toggle) => {
      toggle.addEventListener('change', () => syncCard(toggle));
    });

    function setAll(checked) {
      toggles.forEach((toggle) => {
        toggle.checked = checked;
        syncCard(toggle);
      });
    }

    const selectAll = root.querySelector('[data-qr-select-all]');
    const selectNone = root.querySelector('[data-qr-select-none]');
    if (selectAll) {
      selectAll.addEventListener('click', () => setAll(true));
    }
    if (selectNone) {
      selectNone.addEventListener('click', () => setAll(false));
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-qr-print-controls]').forEach(initQrPrintControls);
  });
})();
