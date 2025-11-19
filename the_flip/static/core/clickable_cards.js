document.addEventListener("DOMContentLoaded", () => {
  const cards = document.querySelectorAll(".js-clickable-card");

  cards.forEach((card) => {
    const targetUrl = card.dataset.url;
    if (!targetUrl) return;

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
  });
});
