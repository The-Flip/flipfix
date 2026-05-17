/**
 * Client-side filtering for the user directory.
 * Filters cards instantly as the user types — same shape as machine_filter.js.
 */
(function () {
  const searchInput = document.getElementById('user-directory-search');
  const list = document.getElementById('user-directory-list');
  const noResults = document.getElementById('user-directory-no-results');

  if (!searchInput || !list) return;

  const items = list.querySelectorAll('[data-search-text]');

  searchInput.addEventListener('input', function () {
    const query = this.value.toLowerCase().trim();
    let matchCount = 0;

    items.forEach((item) => {
      const searchText = item.dataset.searchText.toLowerCase();
      const matches = !query || searchText.includes(query);
      item.classList.toggle('hidden', !matches);
      if (matches) matchCount += 1;
    });

    if (noResults) {
      noResults.classList.toggle('hidden', matchCount > 0);
    }
  });
})();
