document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("log-container");
  const list = document.getElementById("log-list");
  const loading = document.getElementById("log-loading");
  const pagination = document.getElementById("log-pagination");
  const sentinel = document.getElementById("log-sentinel");

  if (!container || !list || !pagination || !sentinel) return;

  const fetchUrl = container.dataset.fetchUrl;
  if (!fetchUrl) return;

  let nextPage = Number(pagination.dataset.nextPage || "0");
  let isLoading = false;

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          loadMore();
        }
      });
    },
    { rootMargin: "200px" }
  );

  if (nextPage > 0) {
    observer.observe(sentinel);
  } else {
    sentinel.remove();
  }

  function loadMore() {
    if (isLoading || nextPage === 0) return;
    isLoading = true;
    loading.classList.remove("hidden");

    const params = new URLSearchParams(window.location.search);
    params.set("page", nextPage);
    fetch(`${fetchUrl}?${params.toString()}`, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.items) {
          const fragment = document.createElement("div");
          fragment.innerHTML = data.items;
          Array.from(fragment.children).forEach((node) => {
            list.appendChild(node);
          });
          if (typeof applySmartDates === "function") {
            applySmartDates(list);
          }
        }
        if (data.has_next) {
          nextPage = data.next_page;
        } else {
          nextPage = 0;
          observer.unobserve(sentinel);
          sentinel.remove();
        }
      })
      .catch((error) => {
        console.error("Failed to load log entries:", error);
      })
      .finally(() => {
        isLoading = false;
        loading.classList.add("hidden");
      });
  }
});
