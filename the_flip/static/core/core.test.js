import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { toDateTimeLocalValue, isSameDay, formatTime, formatRelative } = require('./core.js');

// ── toDateTimeLocalValue ────────────────────────────────────────

describe('toDateTimeLocalValue', () => {
  it('formats date as YYYY-MM-DDTHH:MM', () => {
    expect(toDateTimeLocalValue(new Date(2025, 5, 15, 14, 30))).toBe('2025-06-15T14:30');
  });

  it('zero-pads single-digit months', () => {
    expect(toDateTimeLocalValue(new Date(2025, 0, 15, 10, 0))).toBe('2025-01-15T10:00');
  });

  it('zero-pads single-digit days', () => {
    expect(toDateTimeLocalValue(new Date(2025, 11, 3, 10, 0))).toBe('2025-12-03T10:00');
  });

  it('zero-pads single-digit hours', () => {
    expect(toDateTimeLocalValue(new Date(2025, 5, 15, 8, 30))).toBe('2025-06-15T08:30');
  });

  it('zero-pads single-digit minutes', () => {
    expect(toDateTimeLocalValue(new Date(2025, 5, 15, 14, 5))).toBe('2025-06-15T14:05');
  });

  it('handles midnight (00:00)', () => {
    expect(toDateTimeLocalValue(new Date(2025, 5, 15, 0, 0))).toBe('2025-06-15T00:00');
  });

  it('handles end of year (Dec 31, 23:59)', () => {
    expect(toDateTimeLocalValue(new Date(2025, 11, 31, 23, 59))).toBe('2025-12-31T23:59');
  });
});

// ── isSameDay ───────────────────────────────────────────────────

describe('isSameDay', () => {
  it('returns true for same date at different times', () => {
    const a = new Date(2025, 5, 15, 9, 0);
    const b = new Date(2025, 5, 15, 21, 45);
    expect(isSameDay(a, b)).toBe(true);
  });

  it('returns false for different days in same month', () => {
    const a = new Date(2025, 5, 15, 12, 0);
    const b = new Date(2025, 5, 16, 12, 0);
    expect(isSameDay(a, b)).toBe(false);
  });

  it('returns false for same day in different months', () => {
    const a = new Date(2025, 5, 15, 12, 0);
    const b = new Date(2025, 6, 15, 12, 0);
    expect(isSameDay(a, b)).toBe(false);
  });

  it('returns false for same month/day in different years', () => {
    const a = new Date(2025, 5, 15, 12, 0);
    const b = new Date(2026, 5, 15, 12, 0);
    expect(isSameDay(a, b)).toBe(false);
  });

  it('handles midnight boundary (11:59 PM vs 12:00 AM next day)', () => {
    const a = new Date(2025, 5, 15, 23, 59);
    const b = new Date(2025, 5, 16, 0, 0);
    expect(isSameDay(a, b)).toBe(false);
  });
});

// ── formatTime ──────────────────────────────────────────────────

describe('formatTime', () => {
  it('returns a lowercase string', () => {
    const result = formatTime(new Date(2025, 5, 15, 14, 30));
    expect(result).toBe(result.toLowerCase());
  });

  it('includes minutes when they are non-zero', () => {
    const result = formatTime(new Date(2025, 5, 15, 14, 30));
    expect(result).toMatch(/30/);
  });

  it('omits minutes when they are zero', () => {
    const result = formatTime(new Date(2025, 5, 15, 14, 0));
    // Should not contain :00 — the Intl formatter omits minutes
    expect(result).not.toMatch(/:00/);
  });
});

// ── formatRelative ──────────────────────────────────────────────

describe('formatRelative', () => {
  // Fixed "now": Wednesday, June 18, 2025 at 3:00 PM
  const NOW = new Date(2025, 5, 18, 15, 0);

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows just the time for same day', () => {
    const date = new Date(2025, 5, 18, 9, 30);
    const result = formatRelative(date);
    // Should contain the time digits but no day/date prefix
    expect(result).toMatch(/9/);
    expect(result).toMatch(/30/);
    expect(result).not.toMatch(/yesterday/i);
  });

  it('shows "Yesterday" prefix for yesterday', () => {
    const date = new Date(2025, 5, 17, 10, 0);
    const result = formatRelative(date);
    expect(result).toMatch(/^yesterday/i);
  });

  it('shows weekday abbreviation within 7 days', () => {
    // Saturday June 14 — 4 days before NOW (Wed June 18)
    const date = new Date(2025, 5, 14, 10, 0);
    const result = formatRelative(date);
    // Should contain a short weekday (e.g. "Sat") and not "Yesterday"
    expect(result).not.toMatch(/yesterday/i);
    expect(result.length).toBeGreaterThan(0);
    // Should not include year or month — just weekday + time
    expect(result).not.toMatch(/2025/);
    expect(result).not.toMatch(/jun/i);
  });

  it('shows month and day for same year beyond 7 days', () => {
    // March 10, 2025 — same year, more than 7 days ago
    const date = new Date(2025, 2, 10, 14, 0);
    const result = formatRelative(date);
    // Should contain day number and not the year
    expect(result).toMatch(/10/);
    expect(result).not.toMatch(/2025/);
  });

  it('shows month, day, and year for different year', () => {
    const date = new Date(2024, 11, 25, 9, 0);
    const result = formatRelative(date);
    // Should contain the year
    expect(result).toMatch(/2024/);
    // Should contain the day
    expect(result).toMatch(/25/);
  });
});
