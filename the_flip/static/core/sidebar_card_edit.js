/**
 * Sidebar Card Edit Dropdowns
 *
 * Provides editable dropdowns for sidebar cards (machine selection, problem report selection).
 * Uses data attributes for configuration, auto-initializes on DOMContentLoaded.
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
// Machine Dropdown
// ============================================================

function initSidebarMachineEdit(wrapper) {
  const editBtn = wrapper.querySelector("[data-edit-btn]");
  const dropdown = wrapper.querySelector("[data-dropdown]");
  const searchInput = wrapper.querySelector("[data-search]");
  const listContainer = wrapper.querySelector("[data-list]");

  const apiUrl = wrapper.dataset.apiUrl;
  const currentSlug = wrapper.dataset.currentSlug;
  const csrfToken = wrapper.dataset.csrfToken;

  if (!editBtn || !dropdown || !searchInput || !listContainer || !apiUrl) return;

  let machines = [];

  function hide() {
    dropdown.classList.add("hidden");
  }

  function show() {
    dropdown.classList.remove("hidden");
    searchInput.value = "";
    searchInput.focus();
    if (!machines.length) {
      load();
    } else {
      render("");
    }
  }

  async function load() {
    try {
      const response = await fetch(apiUrl);
      const data = await response.json();
      machines = data.machines || [];
      render("");
    } catch (error) {
      console.error("Failed to load machines:", error);
    }
  }

  function render(query) {
    const q = query.toLowerCase().trim();
    const filtered = q
      ? machines.filter(
          (m) =>
            m.display_name.toLowerCase().includes(q) ||
            m.location.toLowerCase().includes(q) ||
            m.slug.toLowerCase().includes(q)
        )
      : machines;

    if (!filtered.length) {
      listContainer.innerHTML =
        '<div class="sidebar-card-edit-dropdown__item sidebar-card-edit-dropdown__item--none">No machines found</div>';
      return;
    }

    listContainer.innerHTML = filtered
      .map(
        (m) => `
      <button type="button"
              class="sidebar-card-edit-dropdown__item${m.slug === currentSlug ? " sidebar-card-edit-dropdown__item--selected" : ""}"
              data-value="${m.slug}">
        <div>${m.display_name}</div>
        ${m.location ? `<div class="sidebar-card-edit-dropdown__meta">${m.location}</div>` : ""}
      </button>
    `
      )
      .join("");

    listContainer.querySelectorAll("[data-value]").forEach((item) => {
      item.addEventListener("click", () => select(item.dataset.value));
    });
  }

  async function select(slug) {
    if (slug === currentSlug) {
      hide();
      return;
    }

    const formData = new FormData();
    formData.append("action", "update_machine");
    formData.append("machine_slug", slug);
    formData.append("csrfmiddlewaretoken", csrfToken);

    try {
      const response = await fetch(window.location.href, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (data.success && data.status !== "noop") {
        window.location.reload();
      } else if (!data.success) {
        alert(data.error || "Failed to update machine");
      }
      hide();
    } catch (error) {
      console.error("Failed to update machine:", error);
      alert("Failed to update machine");
    }
  }

  // Event listeners
  editBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (dropdown.classList.contains("hidden")) {
      show();
    } else {
      hide();
    }
  });

  searchInput.addEventListener("input", (e) => {
    render(e.target.value);
  });

  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });

  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) {
      hide();
    }
  });
}

// ============================================================
// Problem Report Dropdown
// ============================================================

function initSidebarProblemEdit(wrapper) {
  const editBtn = wrapper.querySelector("[data-edit-btn]");
  const dropdown = wrapper.querySelector("[data-dropdown]");
  const searchInput = wrapper.querySelector("[data-search]");
  const listContainer = wrapper.querySelector("[data-list]");

  const apiUrl = wrapper.dataset.apiUrl;
  const currentId = wrapper.dataset.currentId === "null" ? null : parseInt(wrapper.dataset.currentId, 10);
  const currentMachineSlug = wrapper.dataset.currentMachineSlug;
  const csrfToken = wrapper.dataset.csrfToken;

  if (!editBtn || !dropdown || !searchInput || !listContainer || !apiUrl) return;

  let groups = [];

  function hide() {
    dropdown.classList.add("hidden");
  }

  function show() {
    dropdown.classList.remove("hidden");
    searchInput.value = "";
    searchInput.focus();
    if (!groups.length) {
      load();
    } else {
      render("");
    }
  }

  async function load() {
    try {
      const url = new URL(apiUrl, window.location.origin);
      if (currentMachineSlug) {
        url.searchParams.set("current_machine", currentMachineSlug);
      }
      const response = await fetch(url);
      const data = await response.json();
      groups = data.groups || [];
      render("");
    } catch (error) {
      console.error("Failed to load problem reports:", error);
    }
  }

  function render(query) {
    const q = query.toLowerCase().trim();
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
      const filteredReports = q
        ? group.reports.filter(
            (r) =>
              r.summary.toLowerCase().includes(q) ||
              r.machine_name.toLowerCase().includes(q) ||
              String(r.id).includes(q)
          )
        : group.reports;

      if (filteredReports.length === 0) continue;

      html += `<div class="sidebar-card-edit-dropdown__group">${group.machine_name}</div>`;

      for (const report of filteredReports) {
        const isSelected = report.id === currentId;
        html += `
          <button type="button"
                  class="sidebar-card-edit-dropdown__item${isSelected ? " sidebar-card-edit-dropdown__item--selected" : ""}"
                  data-value="${report.id}">
            <div>#${report.id}: ${report.summary}</div>
          </button>
        `;
      }
    }

    listContainer.innerHTML = html;

    listContainer.querySelectorAll("[data-value]").forEach((item) => {
      item.addEventListener("click", () => select(item.dataset.value));
    });
  }

  async function select(idOrNone) {
    const formData = new FormData();
    formData.append("action", "update_problem_report");
    formData.append("problem_report_id", idOrNone);
    formData.append("csrfmiddlewaretoken", csrfToken);

    try {
      const response = await fetch(window.location.href, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (data.success && data.status !== "noop") {
        window.location.reload();
      } else if (!data.success) {
        alert(data.error || "Failed to update problem report");
      }
      hide();
    } catch (error) {
      console.error("Failed to update problem report:", error);
      alert("Failed to update problem report");
    }
  }

  // Event listeners
  editBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (dropdown.classList.contains("hidden")) {
      show();
    } else {
      hide();
    }
  });

  searchInput.addEventListener("input", (e) => {
    render(e.target.value);
  });

  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });

  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) {
      hide();
    }
  });
}

// ============================================================
// Auto-initialization
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-sidebar-machine-edit]").forEach(initSidebarMachineEdit);
  document.querySelectorAll("[data-sidebar-problem-edit]").forEach(initSidebarProblemEdit);
});
