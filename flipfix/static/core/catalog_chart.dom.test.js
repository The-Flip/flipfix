// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';

const { renderChart } = require('./catalog_chart.js');

const dot = (manufacturer, year, era, extra = {}) => ({
  name: `${manufacturer} ${year}`,
  manufacturer,
  year,
  era,
  era_label: era,
  status: 'good',
  status_label: 'Good',
  url: `/machines/${manufacturer}-${year}/`,
  ...extra,
});

describe('renderChart', () => {
  let mount;

  beforeEach(() => {
    mount = document.createElement('div');
    document.body.appendChild(mount);
  });

  it('draws one linked, era-colored circle per dot', () => {
    renderChart(mount, [
      dot('Williams', 1992, 'SS'),
      dot('Williams', 1992, 'SS'),
      dot('Bally', 1980, 'EM'),
    ]);

    const circles = mount.querySelectorAll('circle.machine-chart__dot');
    expect(circles).toHaveLength(3);

    const links = mount.querySelectorAll('a.machine-chart__dot-link');
    expect(links).toHaveLength(3);
    expect(links[0].getAttribute('href')).toContain('/machines/');
    expect(links[0].getAttribute('aria-label')).toContain('Williams 1992');

    // Era drives the dot class.
    expect(mount.querySelectorAll('.machine-chart__dot--ss')).toHaveLength(2);
    expect(mount.querySelectorAll('.machine-chart__dot--em')).toHaveLength(1);
  });

  it('stacks same-cell dots at the same x but different y', () => {
    renderChart(mount, [dot('Williams', 1992, 'SS'), dot('Williams', 1992, 'SS')]);
    const circles = [...mount.querySelectorAll('circle')];
    expect(circles[0].getAttribute('cx')).toBe(circles[1].getAttribute('cx'));
    expect(circles[0].getAttribute('cy')).not.toBe(circles[1].getAttribute('cy'));
  });

  it('renders a row label per manufacturer and decade gridlines', () => {
    renderChart(mount, [dot('Bally', 1980, 'EM'), dot('Williams', 1992, 'SS')]);
    const rowLabels = [...mount.querySelectorAll('text.machine-chart__row-label')].map(
      (el) => el.textContent
    );
    expect(rowLabels).toContain('Bally');
    expect(rowLabels).toContain('Williams');
    expect(mount.querySelectorAll('line.machine-chart__gridline').length).toBeGreaterThan(0);
  });

  it('reveals the hover card with machine detail on focus', () => {
    renderChart(mount, [dot('Gottlieb', 1975, 'EM', { era_label: 'Electromechanical' })]);
    const card = mount.querySelector('.chart-card');
    expect(card.classList.contains('hidden')).toBe(true);

    mount.querySelector('a.machine-chart__dot-link').dispatchEvent(new Event('mouseenter'));
    expect(card.classList.contains('hidden')).toBe(false);
    expect(card.textContent).toContain('Gottlieb 1975');
    expect(card.textContent).toContain('Electromechanical');
  });

  it('shows an empty message when there are no dots', () => {
    renderChart(mount, []);
    expect(mount.querySelector('svg')).toBeNull();
    expect(mount.textContent).toContain('No machines to chart');
  });
});
