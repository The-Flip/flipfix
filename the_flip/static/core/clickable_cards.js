document.addEventListener("DOMContentLoaded", () => {
  function bindCard(card) {
    const targetUrl = card.dataset.url;
    if (!targetUrl || card.dataset.clickableBound === "true") return;
    card.dataset.clickableBound = "true";

    const navigate = () => {
      window.location.href = targetUrl;
    };

    card.addEventListener("click", navigate);
    card.addEventListener("keypress", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        navigate();
      }
    });
  }

  document.querySelectorAll(".js-clickable-card").forEach(bindCard);

  document.addEventListener("card:initialize", (event) => {
    const node = event.detail;
    if (node && node.classList && node.classList.contains("js-clickable-card")) {
      bindCard(node);
    }
    if (node && node.querySelectorAll) {
      node.querySelectorAll(".js-clickable-card").forEach(bindCard);
    }
  });
});
