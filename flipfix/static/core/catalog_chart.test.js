import { describe, it, expect } from 'vitest';

const {
  groupDots,
  orderManufacturers,
  yearExtent,
  chartYearRange,
  yearScale,
  decadeTicks,
  rowHeight,
} = require('./catalog_chart.js');

const dot = (manufacturer, year, era = 'SS') => ({
  name: `${manufacturer} ${year}`,
  manufacturer,
  year,
  era,
  era_label: era,
  status: 'good',
  status_label: 'Good',
  url: '/machines/x/',
});

describe('groupDots', () => {
  it('groups by manufacturer then year and stacks same-cell machines', () => {
    const groups = groupDots([
      dot('Williams', 1992),
      dot('Williams', 1992),
      dot('Williams', 1990),
      dot('Bally', 1980),
    ]);
    const williams = groups.find((g) => g.manufacturer === 'Williams');
    expect(williams.total).toBe(3);
    expect(williams.maxStack).toBe(2);
    // Stacks are sorted ascending by year.
    expect(williams.stacks.map((s) => s.year)).toEqual([1990, 1992]);
    expect(williams.stacks.find((s) => s.year === 1992).dots).toHaveLength(2);
  });

  it('returns an empty array for no dots', () => {
    expect(groupDots([])).toEqual([]);
  });
});

describe('orderManufacturers', () => {
  it('orders by total descending, then alphabetically', () => {
    const groups = groupDots([
      dot('Stern', 2001),
      dot('Bally', 1980),
      dot('Bally', 1981),
      dot('Atari', 1979),
      dot('Atari', 1980),
    ]);
    expect(orderManufacturers(groups).map((g) => g.manufacturer)).toEqual([
      'Atari', // 2, alphabetically before Bally
      'Bally', // 2
      'Stern', // 1
    ]);
  });
});

describe('yearExtent', () => {
  it('returns min and max years', () => {
    expect(yearExtent([dot('A', 1975), dot('B', 1992), dot('C', 1968)])).toEqual({
      min: 1968,
      max: 1992,
    });
  });

  it('returns null with no dots', () => {
    expect(yearExtent([])).toBeNull();
  });
});

describe('chartYearRange', () => {
  it('extends the domain to the current year even when data is older', () => {
    expect(chartYearRange([dot('A', 1975), dot('B', 1992)], 2026)).toEqual({
      min: 1975,
      max: 2026,
    });
  });

  it('never clips below the data maximum (future-dated data)', () => {
    expect(chartYearRange([dot('A', 1975), dot('B', 2030)], 2026)).toEqual({
      min: 1975,
      max: 2030,
    });
  });

  it('returns null with no dots', () => {
    expect(chartYearRange([], 2026)).toBeNull();
  });
});

describe('yearScale', () => {
  it('maps the domain endpoints to 0 and width', () => {
    const x = yearScale(1970, 1990, 200);
    expect(x(1970)).toBe(0);
    expect(x(1990)).toBe(200);
    expect(x(1980)).toBe(100);
  });

  it('collapses a single-year domain to the midpoint', () => {
    const x = yearScale(1985, 1985, 200);
    expect(x(1985)).toBe(100);
  });
});

describe('decadeTicks', () => {
  it('returns decade boundaries within the range', () => {
    expect(decadeTicks(1968, 1992)).toEqual([1970, 1980, 1990]);
  });

  it('is empty when no decade boundary falls in range', () => {
    expect(decadeTicks(1971, 1978)).toEqual([]);
  });
});

describe('rowHeight', () => {
  it('honours a minimum height for short stacks', () => {
    expect(rowHeight(1)).toBeGreaterThanOrEqual(34);
  });

  it('grows with the tallest stack', () => {
    expect(rowHeight(4)).toBeGreaterThan(rowHeight(1));
  });
});
