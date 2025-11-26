/**
 * Client-side filtering for the machine list.
 * Filters machines instantly as the user types.
 */
(function () {
  const searchInput = document.getElementById("machine-search");
  const machineList = document.getElementById("machine-list");

  if (!searchInput || !machineList) return;

  const items = machineList.querySelectorAll("li[data-search-text]");

  searchInput.addEventListener("input", function () {
    const query = this.value.toLowerCase().trim();

    items.forEach((item) => {
      const searchText = item.dataset.searchText.toLowerCase();
      const matches = !query || searchText.includes(query);
      item.classList.toggle("hidden", !matches);
    });
  });
})();
