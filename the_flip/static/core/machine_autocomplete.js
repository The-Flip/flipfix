function initMachineAutocomplete(container) {
  const input = container.querySelector("[data-machine-search]");
  const hiddenInput = container.querySelector("[data-machine-slug-input]");
  const dropdown = container.querySelector(".autocomplete__dropdown");
  const endpoint = container.dataset.autocompleteUrl;

  if (!input || !hiddenInput || !dropdown || !endpoint) return;

  let results = [];
  let activeIndex = -1;
  let fetchTimeout = null;
  let abortController = null;

  function hideDropdown() {
    dropdown.classList.add("hidden");
    dropdown.innerHTML = "";
    activeIndex = -1;
  }

  function selectMachine(machine) {
    input.value = machine.display_name;
    hiddenInput.value = machine.slug;
    const errorMessages = container.parentElement?.querySelectorAll(".field-error");
    if (errorMessages?.length) {
      errorMessages.forEach((el) => el.remove());
    }
    hideDropdown();
  }

  function renderDropdown(list) {
    if (!list.length) {
      hideDropdown();
      return;
    }
    dropdown.innerHTML = "";

    list.forEach((machine, index) => {
      const item = document.createElement("div");
      item.className = "autocomplete__item";
      if (index === activeIndex) {
        item.classList.add("autocomplete__item-active");
      }
      item.dataset.index = index;
      item.dataset.slug = machine.slug;

      const line = document.createElement("div");
      const nameSpan = document.createElement("span");
      nameSpan.textContent = machine.display_name;
      line.appendChild(nameSpan);

      if (machine.location) {
        const separator = document.createTextNode(" · ");
        const locSpan = document.createElement("span");
        locSpan.className = "text-muted";
        locSpan.textContent = machine.location;
        line.appendChild(separator);
        line.appendChild(locSpan);
      }

      item.appendChild(line);

      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
        selectMachine(machine);
      });

      dropdown.appendChild(item);
    });

    dropdown.classList.remove("hidden");
  }

  function fetchMachines(query) {
    if (fetchTimeout) {
      clearTimeout(fetchTimeout);
    }
    fetchTimeout = setTimeout(() => {
      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();
      const params = new URLSearchParams();
      if (query) {
        params.append("q", query);
      }

      const queryString = params.toString();
      const url = queryString ? `${endpoint}?${queryString}` : endpoint;

      fetch(url, { signal: abortController.signal })
        .then((response) => (response.ok ? response.json() : Promise.reject()))
        .then((data) => {
          results = data.machines || [];
          activeIndex = results.length ? 0 : -1;
          renderDropdown(results);
        })
        .catch((error) => {
          if (error?.name === "AbortError") return;
          hideDropdown();
        });
    }, 150);
  }

  input.addEventListener("focus", () => {
    fetchMachines(input.value.trim());
  });

  input.addEventListener("input", () => {
    hiddenInput.value = "";
    fetchMachines(input.value.trim());
  });

  input.addEventListener("keydown", (event) => {
    if (dropdown.classList.contains("hidden") || !results.length) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, results.length - 1);
      renderDropdown(results);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      renderDropdown(results);
    } else if (event.key === "Enter") {
      if (activeIndex >= 0 && activeIndex < results.length) {
        event.preventDefault();
        selectMachine(results[activeIndex]);
      }
    } else if (event.key === "Escape") {
      hideDropdown();
    }
  });

  document.addEventListener("click", (event) => {
    if (!container.contains(event.target)) {
      hideDropdown();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const containers = document.querySelectorAll("[data-machine-autocomplete]");
  containers.forEach((container) => initMachineAutocomplete(container));
});
