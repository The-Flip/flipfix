/**
 * Machine "Explore" dot chart.
 *
 * Plots physical machines by year (x) and manufacturer (y), colored by
 * technology era. Each dot is one machine; machines sharing a manufacturer and
 * year stack vertically.
 *
 * Data prep lives in pure, exported helpers (groupDots / orderManufacturers /
 * yearScale / yearExtent / decadeTicks). All drawing is funnelled through the
 * single `renderChart` boundary so the rendering layer can later be swapped
 * (e.g. for Observable Plot) without disturbing data prep or the hover card.
 */
(function (exports) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';

  // Layout constants (px).
  const DOT_RADIUS = 7;
  const DOT_PITCH = 18; // vertical center-to-center distance for stacked dots
  const ROW_PADDING = 10;
  const ROW_MIN_HEIGHT = 34;
  const LABEL_GUTTER = 140; // left space for manufacturer names
  const AXIS_HEIGHT = 28; // bottom space for year labels
  const TOP_PAD = 10;
  const RIGHT_PAD = 24;
  const MIN_DECADE_WIDTH = 70;

  // ---- Pure helpers (unit tested) ----------------------------------------

  /**
   * Group dots by manufacturer, then by year.
   * @returns {Array<{manufacturer, total, maxStack, stacks: Array<{year, dots}>}>}
   *   one entry per manufacturer; `stacks` sorted ascending by year.
   */
  function groupDots(dots) {
    const byManufacturer = new Map();
    for (const dot of dots) {
      if (!byManufacturer.has(dot.manufacturer)) {
        byManufacturer.set(dot.manufacturer, new Map());
      }
      const byYear = byManufacturer.get(dot.manufacturer);
      if (!byYear.has(dot.year)) byYear.set(dot.year, []);
      byYear.get(dot.year).push(dot);
    }

    const groups = [];
    for (const [manufacturer, byYear] of byManufacturer) {
      const stacks = [...byYear.entries()]
        .map(([year, stackDots]) => ({ year, dots: stackDots }))
        .sort((a, b) => a.year - b.year);
      const total = stacks.reduce((sum, s) => sum + s.dots.length, 0);
      const maxStack = stacks.reduce((max, s) => Math.max(max, s.dots.length), 0);
      groups.push({ manufacturer, total, maxStack, stacks });
    }
    return groups;
  }

  /** Order manufacturer rows: most machines first, ties broken alphabetically. */
  function orderManufacturers(groups) {
    return [...groups].sort((a, b) => {
      if (b.total !== a.total) return b.total - a.total;
      return a.manufacturer.localeCompare(b.manufacturer);
    });
  }

  /** Min/max year across dots, or null when there are none. */
  function yearExtent(dots) {
    if (!dots.length) return null;
    let min = Infinity;
    let max = -Infinity;
    for (const dot of dots) {
      if (dot.year < min) min = dot.year;
      if (dot.year > max) max = dot.year;
    }
    return { min, max };
  }

  /**
   * Build a linear year→pixel scale over [0, width].
   * Collapses to the midpoint when the domain is a single year.
   */
  function yearScale(minYear, maxYear, width) {
    if (maxYear === minYear) return () => width / 2;
    const span = maxYear - minYear;
    return (year) => ((year - minYear) / span) * width;
  }

  /**
   * Chart x-domain: from the earliest machine to the current year, so the axis
   * always runs through to "now". Guards against future-dated data by never
   * clipping below the data's own maximum.
   */
  function chartYearRange(dots, currentYear) {
    const extent = yearExtent(dots);
    if (!extent) return null;
    return { min: extent.min, max: Math.max(currentYear, extent.max) };
  }

  /** Decade-boundary years within [minYear, maxYear] inclusive. */
  function decadeTicks(minYear, maxYear) {
    const ticks = [];
    for (let y = Math.ceil(minYear / 10) * 10; y <= maxYear; y += 10) {
      ticks.push(y);
    }
    return ticks;
  }

  /** Height of a manufacturer row given its tallest stack. */
  function rowHeight(maxStack) {
    const stackSpan = (Math.max(1, maxStack) - 1) * DOT_PITCH + DOT_RADIUS * 2;
    return Math.max(ROW_MIN_HEIGHT, stackSpan + ROW_PADDING * 2);
  }

  // ---- Rendering (DOM; browser only) -------------------------------------

  function svgEl(name, attrs) {
    const el = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attrs)) {
      el.setAttribute(key, String(value));
    }
    return el;
  }

  function buildHoverCard(mountEl) {
    const card = document.createElement('div');
    card.className = 'chart-card hidden';
    card.setAttribute('role', 'tooltip');
    mountEl.appendChild(card);
    return card;
  }

  function showCard(card, mountEl, circle, dot) {
    card.innerHTML = '';
    const title = document.createElement('div');
    title.className = 'chart-card__title';
    title.textContent = dot.name;
    const meta = document.createElement('div');
    meta.className = 'chart-card__meta';
    meta.textContent = `${dot.manufacturer} · ${dot.year}`;
    const tags = document.createElement('div');
    tags.className = 'chart-card__tags';
    tags.textContent = `${dot.era_label} · ${dot.status_label}`;
    card.append(title, meta, tags);
    card.classList.remove('hidden');

    // Anchor the card to the dot, accounting for horizontal scroll. Clamp so it
    // stays within the (possibly wider-than-viewport) chart canvas.
    const chartRect = mountEl.getBoundingClientRect();
    const dotRect = circle.getBoundingClientRect();
    const left = dotRect.left - chartRect.left + mountEl.scrollLeft + DOT_RADIUS;
    const top = dotRect.top - chartRect.top + mountEl.scrollTop;
    const maxLeft = mountEl.scrollWidth - card.offsetWidth - 8;
    card.style.left = `${Math.max(8, Math.min(left, maxLeft))}px`;
    card.style.top = `${Math.max(8, top - card.offsetHeight - 8)}px`;
  }

  function hideCard(card) {
    card.classList.add('hidden');
  }

  function renderChart(mountEl, dots) {
    mountEl.innerHTML = '';

    if (!dots.length) {
      const empty = document.createElement('p');
      empty.className = 'text-muted';
      empty.textContent = 'No machines to chart yet.';
      mountEl.appendChild(empty);
      return;
    }

    const groups = orderManufacturers(groupDots(dots));
    const extent = chartYearRange(dots, new Date().getFullYear());
    const ticks = decadeTicks(extent.min, extent.max);
    const axisYears = ticks.length
      ? ticks
      : extent.min === extent.max
        ? [extent.min]
        : [extent.min, extent.max];

    const containerWidth = mountEl.clientWidth || 800;
    const minWidth = LABEL_GUTTER + RIGHT_PAD + Math.max(1, axisYears.length) * MIN_DECADE_WIDTH;
    const svgWidth = Math.max(containerWidth, minWidth);
    const plotWidth = svgWidth - LABEL_GUTTER - RIGHT_PAD;
    const xScale = yearScale(extent.min, extent.max, plotWidth);
    const x = (year) => LABEL_GUTTER + xScale(year);

    const rowHeights = groups.map((g) => rowHeight(g.maxStack));
    const plotHeight = rowHeights.reduce((sum, h) => sum + h, 0);
    const svgHeight = TOP_PAD + plotHeight + AXIS_HEIGHT;

    const svg = svgEl('svg', {
      class: 'machine-chart__svg',
      width: svgWidth,
      height: svgHeight,
      viewBox: `0 0 ${svgWidth} ${svgHeight}`,
      role: 'img',
      'aria-label': 'Scatter chart of machines by year and manufacturer, colored by technology era',
    });

    // Decade gridlines + year labels.
    for (const year of axisYears) {
      const px = x(year);
      svg.appendChild(
        svgEl('line', {
          class: 'machine-chart__gridline',
          x1: px,
          y1: TOP_PAD,
          x2: px,
          y2: TOP_PAD + plotHeight,
        })
      );
      const label = svgEl('text', {
        class: 'machine-chart__year-label',
        x: px,
        y: TOP_PAD + plotHeight + 18,
        'text-anchor': 'middle',
      });
      label.textContent = String(year);
      svg.appendChild(label);
    }

    const card = buildHoverCard(mountEl);

    // Manufacturer rows.
    let rowTop = TOP_PAD;
    groups.forEach((group, rowIndex) => {
      const height = rowHeights[rowIndex];
      const baseline = rowTop + height - ROW_PADDING - DOT_RADIUS;

      const label = svgEl('text', {
        class: 'machine-chart__row-label',
        x: LABEL_GUTTER - 10,
        y: rowTop + height / 2,
        'text-anchor': 'end',
        'dominant-baseline': 'middle',
      });
      label.textContent = group.manufacturer;
      svg.appendChild(label);

      for (const stack of group.stacks) {
        stack.dots.forEach((dot, depth) => {
          // Each dot is a link to its machine; the hover/focus card shows detail.
          const link = svgEl('a', {
            class: 'machine-chart__dot-link',
            href: dot.url,
            'aria-label': `${dot.name}, ${dot.manufacturer} ${dot.year}, ${dot.era_label}, ${dot.status_label}`,
          });
          const circle = svgEl('circle', {
            class: `machine-chart__dot machine-chart__dot--${dot.era.toLowerCase()}`,
            cx: x(dot.year),
            cy: baseline - depth * DOT_PITCH,
            r: DOT_RADIUS,
          });
          link.appendChild(circle);
          const show = () => showCard(card, mountEl, circle, dot);
          link.addEventListener('mouseenter', show);
          link.addEventListener('focus', show);
          link.addEventListener('mouseleave', () => hideCard(card));
          link.addEventListener('blur', () => hideCard(card));
          svg.appendChild(link);
        });
      }
      rowTop += height;
    });

    mountEl.appendChild(svg);
  }

  function init(mountEl) {
    const dataEl = document.getElementById('machine-chart-data');
    if (!dataEl) return;
    let dots;
    try {
      dots = JSON.parse(dataEl.textContent);
    } catch (err) {
      return;
    }
    renderChart(mountEl, dots);

    // Redraw on resize so the year axis re-fits the viewport.
    let resizeTimer;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => renderChart(mountEl, dots), 150);
    });
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
      const mountEl = document.querySelector('[data-machine-chart]');
      if (mountEl) init(mountEl);
    });
  }

  if (exports) {
    exports.groupDots = groupDots;
    exports.orderManufacturers = orderManufacturers;
    exports.yearExtent = yearExtent;
    exports.chartYearRange = chartYearRange;
    exports.yearScale = yearScale;
    exports.decadeTicks = decadeTicks;
    exports.rowHeight = rowHeight;
    exports.renderChart = renderChart;
  }
})(typeof module !== 'undefined' ? module.exports : null);
