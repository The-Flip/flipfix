/**
 * Text Edit Module
 *
 * Provides inline editing functionality for text cards with markdown rendering.
 * Auto-initializes on elements with [data-text-card] attribute.
 *
 * Expected HTML structure (from text_card_editable.html partial):
 *   <div data-text-card>
 *     <button data-text-edit-btn>Edit</button>
 *     <div data-text-edit-actions class="hidden">
 *       <button data-text-save-btn>Save</button>
 *       <button data-text-cancel-btn>Cancel</button>
 *     </div>
 *     <span data-text-status></span>
 *     <div data-text-view-mode>
 *       <div data-text-display>...rendered markdown...</div>
 *     </div>
 *     <div data-text-edit-mode class="hidden">
 *       <textarea data-text-textarea>...raw text...</textarea>
 *     </div>
 *   </div>
 *
 * CSRF token is read from the csrftoken cookie (set by Django).
 *
 * POST payload:
 *   action: 'update_text'
 *   text: <textarea value>
 *   csrfmiddlewaretoken: <CSRF_TOKEN>
 */

(function () {
  "use strict";

  function getCsrfToken() {
    const cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : "";
  }

  function initTextCard(card) {
    const editBtn = card.querySelector("[data-text-edit-btn]");
    const editActions = card.querySelector("[data-text-edit-actions]");
    const saveBtn = card.querySelector("[data-text-save-btn]");
    const cancelBtn = card.querySelector("[data-text-cancel-btn]");
    const statusEl = card.querySelector("[data-text-status]");
    const viewMode = card.querySelector("[data-text-view-mode]");
    const editMode = card.querySelector("[data-text-edit-mode]");
    const textarea = card.querySelector("[data-text-textarea]");

    if (!editBtn || !textarea || !viewMode || !editMode) {
      console.warn("Text card missing required elements", card);
      return;
    }

    let originalText = textarea.value;

    function setTextareaHeight() {
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
      textarea.style.overflowY = "hidden";
    }

    function enterEditMode() {
      originalText = textarea.value;
      viewMode.classList.add("hidden");
      editMode.classList.remove("hidden");
      editBtn.classList.add("hidden");
      if (editActions) editActions.classList.remove("hidden");
      textarea.focus();
      setTextareaHeight();
      requestAnimationFrame(setTextareaHeight);
    }

    function exitEditMode() {
      textarea.value = originalText;
      if (statusEl) {
        statusEl.textContent = "";
        statusEl.className = "status-indicator";
      }
      editMode.classList.add("hidden");
      viewMode.classList.remove("hidden");
      if (editActions) editActions.classList.add("hidden");
      editBtn.classList.remove("hidden");
    }

    async function saveText() {
      if (statusEl) {
        statusEl.textContent = "Saving...";
        statusEl.className = "status-indicator saving";
      }

      try {
        const formData = new FormData();
        formData.append("action", "update_text");
        formData.append("text", textarea.value);
        formData.append("csrfmiddlewaretoken", getCsrfToken());

        const response = await fetch(window.location.href, {
          method: "POST",
          body: formData,
        });

        if (response.ok) {
          // Reload to show rendered markdown
          window.location.reload();
        } else {
          if (statusEl) {
            statusEl.textContent = "Error saving";
            statusEl.className = "status-indicator error";
          }
        }
      } catch (error) {
        console.error("Save error:", error);
        if (statusEl) {
          statusEl.textContent = "Error saving";
          statusEl.className = "status-indicator error";
        }
      }
    }

    // Event listeners
    editBtn.addEventListener("click", enterEditMode);
    textarea.addEventListener("input", setTextareaHeight);

    if (cancelBtn) {
      cancelBtn.addEventListener("click", exitEditMode);
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", saveText);
    }
  }

  function init() {
    document.querySelectorAll("[data-text-card]").forEach(initTextCard);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
