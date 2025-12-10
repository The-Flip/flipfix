/**
 * Sidebar Card Edit Dropdowns
 *
 * Provides editable dropdowns for sidebar cards (machine selection, problem report selection).
 * Uses data attributes for configuration, auto-initializes on DOMContentLoaded.
 *
 * Requires: dropdown_keyboard.js, searchable_dropdown.js
 *
 * Usage:
 *   <div data-sidebar-machine-edit
 *        data-api-url="/api/machines/"
 *        data-current-slug="machine-slug"
 *        data-csrf-token="...">
 *
 *   <div data-sidebar-problem-edit
 *        data-api-url="/api/problem-reports/"
 *        data-current-id="123"
 *        data-current-machine-slug="machine-slug"
 *        data-csrf-token="...">
 */

// ============================================================
// Shared Utilities
// ============================================================

/**
 * Escape HTML special characters to prevent XSS.
 */
function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * POST a form action to the current page and reload on success.
 */
async function postAction(action, valueKey, value, csrfToken) {
  const formData = new FormData();
  formData.append("action", action);
  formData.append(valueKey, value);
  formData.append("csrfmiddlewaretoken", csrfToken);

  const response = await fetch(window.location.href, {
    method: "POST",
    body: formData,
  });

  const data = await response.json();
  if (data.success && data.status !== "noop") {
    window.location.reload();
  } else if (!data.success) {
    throw new Error(data.error || "Operation failed");
  }
}

/**
 * Filter items by query against multiple fields.
 */
function filterByQuery(items, query, getSearchableText) {
  if (!query) return items;
  const q = query.toLowerCase().trim();
  return items.filter((item) => getSearchableText(item).toLowerCase().includes(q));
}

// ============================================================
// Machine Dropdown
// ============================================================

function initSidebarMachineEdit(wrapper) {
  const apiUrl = wrapper.dataset.apiUrl;
  const currentSlug = wrapper.dataset.currentSlug;
  const csrfToken = wrapper.dataset.csrfToken;

  if (!apiUrl) return;

  createSearchableDropdown({
    wrapper,

    loadData: async () => {
      const response = await fetch(apiUrl);
      const json = await response.json();
      return json.machines || [];
    },

    renderItems: (machines, query) => {
      const filtered = filterByQuery(machines, query, (m) =>
        [m.display_name, m.location, m.slug].join(" ")
      );

      if (!filtered.length) {
        return '<div class="sidebar-card-edit-dropdown__item sidebar-card-edit-dropdown__item--none">No machines found</div>';
      }

      return filtered
        .map(
          (m) => `
        <button type="button"
                class="sidebar-card-edit-dropdown__item${m.slug === currentSlug ? " sidebar-card-edit-dropdown__item--selected" : ""}"
                data-value="${escapeHtml(m.slug)}">
          <div>${escapeHtml(m.display_name)}</div>
          ${m.location ? `<div class="sidebar-card-edit-dropdown__meta">${escapeHtml(m.location)}</div>` : ""}
        </button>
      `
        )
        .join("");
    },

    onSelect: async (slug) => {
      if (slug === currentSlug) return;
      await postAction("update_machine", "machine_slug", slug, csrfToken);
    },
  });
}

// ============================================================
// Problem Report Dropdown
// ============================================================

function initSidebarProblemEdit(wrapper) {
  const apiUrl = wrapper.dataset.apiUrl;
  const currentId =
    wrapper.dataset.currentId === "null"
      ? null
      : parseInt(wrapper.dataset.currentId, 10);
  const currentMachineSlug = wrapper.dataset.currentMachineSlug;
  const csrfToken = wrapper.dataset.csrfToken;

  if (!apiUrl) return;

  createSearchableDropdown({
    wrapper,

    loadData: async () => {
      const url = new URL(apiUrl, window.location.origin);
      if (currentMachineSlug) {
        url.searchParams.set("current_machine", currentMachineSlug);
      }
      const response = await fetch(url);
      const json = await response.json();
      return json.groups || [];
    },

    renderItems: (groups, query) => {
      let html = "";

      // Always show "None" option first
      html += `
        <button type="button"
                class="sidebar-card-edit-dropdown__item sidebar-card-edit-dropdown__item--none${currentId === null ? " sidebar-card-edit-dropdown__item--selected" : ""}"
                data-value="none">
          None (unlink from problem)
        </button>
      `;

      // Filter and render groups
      for (const group of groups) {
        const filteredReports = filterByQuery(group.reports, query, (r) =>
          [r.summary, r.machine_name, String(r.id)].join(" ")
        );

        if (filteredReports.length === 0) continue;

        html += `<div class="sidebar-card-edit-dropdown__group">${escapeHtml(group.machine_name)}</div>`;

        for (const report of filteredReports) {
          const isSelected = report.id === currentId;
          html += `
            <button type="button"
                    class="sidebar-card-edit-dropdown__item${isSelected ? " sidebar-card-edit-dropdown__item--selected" : ""}"
                    data-value="${report.id}">
              <div>#${report.id}: ${escapeHtml(report.summary)}</div>
            </button>
          `;
        }
      }

      return html;
    },

    onSelect: async (idOrNone) => {
      await postAction(
        "update_problem_report",
        "problem_report_id",
        idOrNone,
        csrfToken
      );
    },
  });
}

// ============================================================
// Auto-initialization
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  document
    .querySelectorAll("[data-sidebar-machine-edit]")
    .forEach(initSidebarMachineEdit);
  document
    .querySelectorAll("[data-sidebar-problem-edit]")
    .forEach(initSidebarProblemEdit);
});
