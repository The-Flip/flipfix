function applySmartDates(root = document) {
  const dateNodes = root.querySelectorAll(".smart-date");
  dateNodes.forEach((node) => {
    const iso = node.getAttribute("datetime");
    if (!iso) return;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return;

    node.textContent = formatRelative(date);
  });
}

document.addEventListener("DOMContentLoaded", () => applySmartDates());

function formatTime(date) {
  const minutes = date.getMinutes();
  const formatter = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: minutes === 0 ? undefined : "2-digit",
  });
  return formatter.format(date).toLowerCase();
}

function formatRelative(date) {
  const now = new Date();
  const diffMs = now - date;
  const oneDay = 24 * 60 * 60 * 1000;

  const sameDay = isSameDay(date, now);
  const yesterday = isSameDay(
    date,
    new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
  );

  if (sameDay) {
    return formatTime(date);
  }

  if (yesterday) {
    return `Yesterday ${formatTime(date)}`;
  }

  if (diffMs < 7 * oneDay) {
    const weekday = new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(
      date
    );
    return `${weekday} ${formatTime(date)}`;
  }

  if (date.getFullYear() === now.getFullYear()) {
    const monthDay = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(date);
    return `${monthDay} ${formatTime(date)}`;
  }

  const full = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
  return `${full} ${formatTime(date)}`;
}

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}
